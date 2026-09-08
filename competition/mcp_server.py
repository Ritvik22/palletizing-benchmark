"""Stdio MCP connector to the public API. Credentials stay in the environment.

Stdio deliberately needs no hosted OAuth authorization server. Researchers sign
in on the website, issue a scoped, expiring API token, and configure their MCP
client once. Every tool calls the SAME authenticated HTTP service as the UI.
"""
import os
from typing import Any
from urllib.parse import urlparse
import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

server=FastMCP('Palletizing Benchmark')
READ=ToolAnnotations(readOnlyHint=True,destructiveHint=False)
WRITE=ToolAnnotations(readOnlyHint=False,destructiveHint=False)


async def api(method,path,data=None):
    origin=os.getenv('PALLETIZING_API_URL','https://palletizing-benchmark.org').rstrip('/')
    parsed=urlparse(origin)
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path:
        raise ValueError('PALLETIZING_API_URL must be a plain origin.')
    if parsed.scheme!='https' and not (parsed.scheme=='http' and parsed.hostname in ('127.0.0.1','localhost','::1')):
        raise ValueError('The competition API must use HTTPS outside loopback.')
    token=os.getenv('PALLETIZING_API_TOKEN','')
    async with httpx.AsyncClient(base_url=origin,timeout=120,follow_redirects=False) as client:
        response=await client.request(method,path,json=data,headers={'Authorization':'Bearer '+token} if token else {})
    if response.status_code>=400:
        try:
            reason=response.json().get('detail','Request failed')
        except ValueError:
            reason='Request failed'
        raise ValueError(f'Competition API {response.status_code}: {reason}')
    return response.json()


def segment(value):
    from urllib.parse import quote
    return quote(value,safe='')


@server.tool(annotations=READ)
async def list_benchmarks()->list[dict[str,Any]]:
    """List immutable benchmarks, their rules, sizes, and dataset hashes."""
    return await api('GET','/api/benchmarks')


@server.tool(annotations=READ)
async def get_benchmark(benchmark_id:str)->dict:
    """Read rules, hash and bulk download URL. Use list_orders/get_order for bounded agent context."""
    return await api('GET','/api/benchmarks/'+segment(benchmark_id)+'/manifest')


@server.tool(annotations=READ)
async def list_orders(benchmark_id:str,offset:int=0,limit:int=25)->dict:
    """Page through benchmark order IDs and box counts; maximum page size 100."""
    return await api('GET','/api/benchmarks/'+segment(benchmark_id)+f'/orders?offset={offset}&limit={limit}')


@server.tool(annotations=READ)
async def get_order(benchmark_id:str,order_id:str)->dict:
    """Read one order, its canonical box identities and authoritative dimensions/weights."""
    return await api('GET','/api/benchmarks/'+segment(benchmark_id)+'/orders/'+segment(order_id))


@server.tool(annotations=READ)
async def get_pack_schema()->dict:
    """Get the exact upload schema. Positions are box centres in metres; rotations 0/90."""
    return await api('GET','/api/schema/pack')


@server.tool(annotations=READ)
async def list_my_strategies()->list[dict[str,Any]]:
    """List your strategies and draft/published revisions."""
    return await api('GET','/api/mine')


@server.tool(annotations=WRITE)
async def create_strategy(name:str,description:str='')->dict:
    """Create a named strategy owned by the signed-in researcher."""
    return await api('POST','/api/strategies',{'name':name,'description':description})


@server.tool(annotations=WRITE)
async def create_revision(strategy_id:str,benchmark_id:str,notes:str,code_revision:str,
                          model_revision:str='not-applicable',parent_id:str|None=None,config:dict|None=None)->dict:
    """Create a draft; optionally inherit all packs from your published parent. No leaderboard change yet."""
    return await api('POST','/api/strategies/'+segment(strategy_id)+'/revisions',
                     dict(benchmark_id=benchmark_id,notes=notes,code_revision=code_revision,
                          model_revision=model_revision,parent_id=parent_id,config=config or {}))


@server.tool(annotations=ToolAnnotations(readOnlyHint=False,destructiveHint=True))
async def upload_packs(revision_id:str,packs:list[dict])->dict:
    """Upload up to 25 packs and receive server validation. Replaces those orders in YOUR DRAFT only."""
    return await api('PUT','/api/revisions/'+segment(revision_id)+'/packs',{'packs':packs})


@server.tool(annotations=READ)
async def get_revision(revision_id:str)->dict:
    """Read revision metadata, per-order errors and fixed-denominator benchmark totals."""
    return await api('GET','/api/revisions/'+segment(revision_id))


@server.tool(annotations=WRITE)
async def publish_revision(revision_id:str,confirm:bool=False)->dict:
    """Make a revision public and immutable. Ask the researcher before setting confirm=true. Requires publish scope."""
    if not confirm:
        raise ValueError('Publication needs explicit confirmation; set confirm=true only after researcher approval.')
    return await api('POST','/api/revisions/'+segment(revision_id)+'/publish')


@server.tool(annotations=READ)
async def compare_revisions(left:str,right:str)->dict:
    """Compare revisions on the same benchmark; LVE uses their common completed orders."""
    return await api('GET','/api/revisions/'+segment(left)+'/compare/'+segment(right))


@server.tool(annotations=READ)
async def get_leaderboard(benchmark_id:str)->list[dict[str,Any]]:
    """List published revisions. Only complete benchmark runs have a compactness rank."""
    return await api('GET','/api/benchmarks/'+segment(benchmark_id)+'/leaderboard')


def main():
    server.run(transport='stdio')


if __name__=='__main__':
    main()
