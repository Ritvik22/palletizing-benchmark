"""Provider verification is tested with locally signed tokens; no Google traffic."""
import time
from urllib.parse import parse_qs,urlparse

from cryptography.hazmat.primitives.asymmetric import rsa
import httpx
import jwt
import pytest
from fastapi.testclient import TestClient

from competition.app import create_app
from competition.config import Settings


@pytest.mark.parametrize('fault',[None,'audience','issuer','nonce','expired','unverified','authorized-party','signature'])
def test_google_token_verification(tmp_path,monkeypatch,fault):
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    jwk=jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(),as_dict=True);jwk['kid']='test'
    app=create_app(Settings(database=str(tmp_path/'google.sqlite'),google_client_id='client-id',google_client_secret='test-only'))
    with TestClient(app,base_url='http://127.0.0.1:8769') as client:
        start=client.get('/api/auth/google',follow_redirects=False)
        query=parse_qs(urlparse(start.headers['location']).query)
        claims={'iss':'https://accounts.google.com','aud':'client-id','sub':'google-subject',
                'iat':int(time.time()),'exp':int(time.time())+300,'nonce':query['nonce'][0],
                'email':'researcher@example.test','email_verified':True,'name':'Researcher'}
        if fault=='audience':claims['aud']='another-app'
        if fault=='issuer':claims['iss']='https://attacker.example'
        if fault=='nonce':claims['nonce']='wrong'
        if fault=='expired':claims['exp']=int(time.time())-60
        if fault=='unverified':claims['email_verified']=False
        if fault=='authorized-party':claims['azp']='another-app'
        signing_key=rsa.generate_private_key(public_exponent=65537,key_size=2048) if fault=='signature' else key
        signed=jwt.encode(claims,signing_key,algorithm='RS256',headers={'kid':'test'})

        class Provider:
            def __init__(self,**kwargs):pass
            async def __aenter__(self):return self
            async def __aexit__(self,*args):pass
            async def post(self,url,data):
                assert data['code_verifier'] and data['client_id']=='client-id'
                return httpx.Response(200,json={'id_token':signed},request=httpx.Request('POST',url))
            async def get(self,url):
                assert url=='https://www.googleapis.com/oauth2/v3/certs'
                return httpx.Response(200,json={'keys':[jwk]},request=httpx.Request('GET',url))

        monkeypatch.setattr('competition.auth.httpx.AsyncClient',Provider)
        result=client.get('/api/auth/google/callback',params={'state':query['state'][0],'code':'test-code'},follow_redirects=False)
        assert result.status_code==(400 if fault else 303)
        assert bool(client.get('/api/auth/me').json()['user']) is (fault is None)
        assert client.get('/api/auth/google/callback',params={'state':query['state'][0],'code':'replay'}).status_code==400
