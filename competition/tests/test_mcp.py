"""Real MCP stdio client -> connector process -> HTTP API -> SQLite/evaluator."""
import asyncio
from contextlib import contextmanager
import json
import socket
import sys
from pathlib import Path
import threading
import time

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import uvicorn

from competition.app import create_app
from competition.config import Settings
from competition.tests.test_competition import benchmark, pack


@contextmanager
def running_api(tmp_path):
    sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(128)
    port=sock.getsockname()[1];origin=f'http://127.0.0.1:{port}'
    app=create_app(Settings(database=str(tmp_path/'mcp.sqlite'),origin=origin))
    app.state.store.add_benchmark(benchmark())
    user=app.state.store.user('test','mcp','MCP test','mcp@example.test')
    token=app.state.store.credential(user['id'],'test',['submit','publish'],60)
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error',access_log=False))
    thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
    try:
        for _ in range(100):
            if server.started:break
            time.sleep(.02)
        assert server.started
        yield origin,token,app.state.store
    finally:
        server.should_exit=True;thread.join(timeout=10);sock.close()


@pytest.mark.parametrize('launch',['module','installed-command'])
def test_stdio_submission_and_revision_round_trip(tmp_path,launch):
    async def journey(origin,token):
        command,args=sys.executable,['-m','competition.mcp_server']
        if launch=='installed-command':
            command=str(Path(sys.executable).parent/('palletizing-mcp.exe' if sys.platform=='win32' else 'palletizing-mcp'))
            assert Path(command).is_file(),'Install the project first: python -m pip install --no-deps -e .'
            args=[]
        params=StdioServerParameters(command=command,args=args,cwd=str(tmp_path),
                                    env={'PALLETIZING_API_URL':origin,'PALLETIZING_API_TOKEN':token})
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as session:
                await session.initialize()
                tools=await session.list_tools()
                assert len(tools.tools)==13
                async def call(name,args=None):
                    result=await session.call_tool(name,args or {})
                    assert not result.isError,(name,result)
                    content=result.structuredContent
                    if content is not None:
                        return content['result'] if set(content)=={'result'} else content
                    return json.loads(result.content[0].text)
                benches=await call('list_benchmarks')
                # FastMCP may wrap list results in structured content, but text remains JSON.
                assert benches[0]['id']=='tiny-v1'
                assert (await call('list_orders',{'benchmark_id':'tiny-v1','limit':1}))['next_offset']==1
                assert (await call('get_order',{'benchmark_id':'tiny-v1','order_id':'one'}))['instances'][0]['id']=='a:0000'
                assert (await call('get_pack_schema'))['title']=='Pack'
                sid=(await call('create_strategy',{'name':'MCP-only strategy'}))['id']
                rid=(await call('create_revision',{'strategy_id':sid,'benchmark_id':'tiny-v1','notes':'Initial','code_revision':'test'}))['id']
                await call('upload_packs',{'revision_id':rid,'packs':[pack(),pack('two')]})
                report=await call('get_revision',{'revision_id':rid})
                assert report['summary']['orders_complete']==2
                unconfirmed=await session.call_tool('publish_revision',{'revision_id':rid})
                assert unconfirmed.isError
                await call('publish_revision',{'revision_id':rid,'confirm':True})
                entries=await call('get_leaderboard',{'benchmark_id':'tiny-v1'})
                assert entries[0]['rank']==1
                child=(await call('create_revision',{'strategy_id':sid,'benchmark_id':'tiny-v1','notes':'Child','code_revision':'v2','parent_id':rid}))['id']
                assert (await call('compare_revisions',{'left':rid,'right':child}))['changed_orders']==[]
    with running_api(tmp_path) as (origin,token,store):
        asyncio.run(journey(origin,token))
