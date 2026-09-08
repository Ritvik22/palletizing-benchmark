"""Google OIDC + one-use, browser-bound email links. No default passwords."""
from email.message import EmailMessage
from ipaddress import ip_address
import re
import secrets
import smtplib
import ssl
import time
from urllib.parse import urlencode

import httpx
from authlib.jose import JsonWebToken
from fastapi import APIRouter, Request
from starlette.responses import JSONResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool

from .models import EmailRequest, StrictModel, TokenRequest
from .store import Problem, token_hash
from pydantic import Field

GOOGLE_ISSUER = 'https://accounts.google.com'
GOOGLE_JWKS = 'https://www.googleapis.com/oauth2/v3/certs'
COOKIE = 'competition_session'


class EmailFinish(StrictModel):
    token: str


class LocalAdminLogin(StrictModel):
    username: str = Field(min_length=1,max_length=80)
    password: str = Field(min_length=1,max_length=200)


def local_admin_allowed(request):
    """Explicit opt-in, direct loopback requests only; never trust forwarding headers."""
    if not request.app.state.settings.local_admin_login or not request.client:
        return False
    if any(name in request.headers for name in ('forwarded','x-forwarded-for','x-forwarded-host','x-forwarded-proto')):
        return False
    try:
        return ip_address(request.client.host).is_loopback
    except ValueError:
        return False


def principal(request: Request, required=None, session_only=False):
    store, settings = request.app.state.store, request.app.state.settings
    header = request.headers.get('authorization','')
    bearer = header.startswith('Bearer ')
    raw = header[7:] if bearer else request.cookies.get(COOKIE)
    user = store.authenticate(raw)
    if not user or (session_only and 'session' not in user['scopes']):
        raise Problem(401,'Please sign in.')
    # Even an existing session/API token copied in a DB backup must fail closed.
    if user['provider']=='local-admin' and not local_admin_allowed(request):
        raise Problem(401,'Local preview accounts are disabled here.')
    if bearer and 'session' in user['scopes']:
        raise Problem(401,'Use an API token, not a browser session.')
    if not bearer and 'session' not in user['scopes']:
        raise Problem(401,'Invalid browser session.')
    if required and required not in user['scopes']:
        raise Problem(403,f'This token does not have {required} permission.')
    if request.method not in ('GET','HEAD','OPTIONS') and not bearer:
        if request.headers.get('origin') != settings.origin:
            raise Problem(403,'Request origin does not match this website.')
    return user


def optional_user(request):
    try:
        return principal(request)
    except Problem:
        return None


def session_response(store,settings,user,redirect=False):
    token = store.credential(user['id'],'Browser session',['session','submit','publish'],86400*7)
    response = RedirectResponse('/',status_code=303) if redirect else JSONResponse({'ok':True})
    response.set_cookie(COOKIE,token,httponly=True,secure=settings.secure,samesite='lax',max_age=86400*7,path='/')
    response.delete_cookie('competition_flow',path='/')
    response.headers['Cache-Control']='no-store'
    return response


def send_mail(settings,email,link):
    message=EmailMessage()
    message['Subject']='Sign in to Palletizing Benchmark'
    message['From']=settings.mail_from
    message['To']=email
    message.set_content('You requested a sign-in link for Palletizing Benchmark.\n\n'+link+
                        '\n\nOpen it in the browser where you requested it. It expires in 10 minutes and works once. '
                        'If you did not request this, ignore this email.')
    with smtplib.SMTP(settings.smtp_host,settings.smtp_port,timeout=15) as smtp:
        smtp.starttls(context=ssl.create_default_context())
        smtp.login(settings.smtp_username,settings.smtp_password)
        smtp.send_message(message)


def routes(store,settings):
    router=APIRouter(prefix='/api/auth')

    @router.get('/options')
    def options(request:Request):
        return {'google':settings.google_enabled,'email':settings.email_enabled,
                'local_admin':local_admin_allowed(request),
                'configured':settings.google_enabled or settings.email_enabled}

    @router.post('/local-admin')
    def local_admin(request:Request,data:LocalAdminLogin):
        if not local_admin_allowed(request):
            raise Problem(404,'Local preview sign-in is disabled.')
        if request.headers.get('origin') != settings.origin:
            raise Problem(403,'Request origin does not match this website.')
        store.limit('local-admin:'+request.client.host,10,600)
        if not (secrets.compare_digest(data.username.encode(),b'admin') &
                secrets.compare_digest(data.password.encode(),b'admin')):
            raise Problem(401,'Incorrect local username or password.')
        user=store.user('local-admin','admin','Local admin','admin@localhost')
        return session_response(store,settings,user)

    @router.get('/me')
    def me(request:Request):
        user=optional_user(request)
        return {'user':None if not user else {'id':user['id'],'name':user['display_name'],'email':user['email']}}

    @router.post('/logout')
    def logout(request:Request):
        user=principal(request,session_only=True)
        with store.connect(True) as db:
            db.execute('DELETE FROM credentials WHERE hash=?',(user['credential_id'],))
        response=JSONResponse({'ok':True});response.delete_cookie(COOKIE,path='/')
        return response

    @router.get('/google')
    def google(request:Request):
        if not settings.google_enabled:
            raise Problem(503,'Google sign-in is not configured.')
        store.limit('google:'+(request.client.host if request.client else ''),10,600)
        binding=secrets.token_urlsafe(32)
        verifier=secrets.token_urlsafe(48)
        import base64,hashlib
        challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        nonce=secrets.token_urlsafe(32)
        state=store.ticket('google',{'binding':token_hash(binding),'nonce':nonce,'verifier':verifier})
        query=urlencode({'client_id':settings.google_client_id,'redirect_uri':settings.origin+'/api/auth/google/callback',
                         'response_type':'code','scope':'openid email profile','state':state,'nonce':nonce,
                         'code_challenge':challenge,'code_challenge_method':'S256'})
        response=RedirectResponse(GOOGLE_ISSUER+'/o/oauth2/v2/auth?'+query)
        response.set_cookie('competition_flow',binding,httponly=True,secure=settings.secure,samesite='lax',max_age=600,path='/')
        return response

    @router.get('/google/callback')
    async def callback(request:Request,state:str='',code:str=''):
        if not settings.google_enabled or not state or not code or len(state)>200 or len(code)>4096:
            raise Problem(400,'Google sign-in was not completed. Please try again.')
        payload=store.consume_ticket('google',state,request.cookies.get('competition_flow'))
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                result=await client.post('https://oauth2.googleapis.com/token',data={
                    'client_id':settings.google_client_id,'client_secret':settings.google_client_secret,'code':code,
                    'grant_type':'authorization_code','code_verifier':payload['verifier'],
                    'redirect_uri':settings.origin+'/api/auth/google/callback'})
                result.raise_for_status()
                keys=await client.get(GOOGLE_JWKS);keys.raise_for_status()
            claims=JsonWebToken(['RS256']).decode(result.json()['id_token'],keys.json(),claims_options={
                'iss':{'essential':True,'value':GOOGLE_ISSUER},'aud':{'essential':True,'value':settings.google_client_id},
                'exp':{'essential':True},'iat':{'essential':True},'sub':{'essential':True},
                'nonce':{'essential':True,'value':payload['nonce']}})
            claims.validate(leeway=30)
            if claims.get('email_verified') is not True or not claims.get('email'):
                raise ValueError('Unverified Google email')
            if claims.get('azp',settings.google_client_id) != settings.google_client_id:
                raise ValueError('Invalid authorized party')
        except Exception as e:
            raise Problem(400,'Google identity could not be verified. Please try again.') from e
        user=store.user('google',claims['sub'],claims.get('name') or claims['email'].split('@')[0],claims['email'])
        return session_response(store,settings,user,True)

    @router.post('/email')
    async def email_start(request:Request,data:EmailRequest):
        if not settings.email_enabled:
            raise Problem(503,'Email sign-in is not configured.')
        if request.headers.get('origin') != settings.origin:
            raise Problem(403,'Request origin does not match this website.')
        address=data.email.strip().lower()
        if not re.fullmatch(r'[A-Za-z0-9.!#$%&\x27*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}',address):
            raise Problem(422,'Enter a valid email address.')
        store.limit('email-ip:'+(request.client.host if request.client else ''),5,600)
        store.limit('email-address:'+address,3,600)
        binding=secrets.token_urlsafe(32)
        token=store.ticket('email',{'binding':token_hash(binding),'email':address})
        try:
            # A fragment keeps the token out of proxy/server access logs.
            await run_in_threadpool(send_mail,settings,address,settings.origin+'/#sign-in='+token)
        except Exception as e:
            raise Problem(503,'Email could not be sent. Please try again later.') from e
        response=JSONResponse({'ok':True,'message':'Check your email for a sign-in link.'})
        response.set_cookie('competition_flow',binding,httponly=True,secure=settings.secure,samesite='lax',max_age=600,path='/')
        return response

    @router.post('/email/finish')
    def email_finish(request:Request,data:EmailFinish):
        if not settings.email_enabled or len(data.token)>200:
            raise Problem(400,'Email sign-in is unavailable.')
        if request.headers.get('origin') != settings.origin:
            raise Problem(403,'Request origin does not match this website.')
        store.limit('email-finish:'+(request.client.host if request.client else ''),20,600)
        payload=store.consume_ticket('email',data.token,request.cookies.get('competition_flow'))
        user=store.user('email',payload['email'],payload['email'].split('@')[0],payload['email'])
        return session_response(store,settings,user)

    @router.post('/tokens')
    def create_token(request:Request,data:TokenRequest):
        user=principal(request,session_only=True)
        store.limit('new-token:'+user['id'],10,3600)
        if not data.scopes:
            raise Problem(422,'Choose at least one token permission.')
        raw=store.credential(user['id'],data.name,sorted(set(data.scopes)),data.days*86400)
        return {'token':raw,'expires_in_days':data.days,'scopes':data.scopes}

    @router.get('/tokens')
    def list_tokens(request:Request):
        user=principal(request,session_only=True)
        with store.connect() as db:
            rows=db.execute('SELECT hash AS id,name,scopes,expires,created FROM credentials WHERE user_id=? AND expires>?',
                            (user['id'],time.time())).fetchall()
        import json
        return [dict(r)|{'scopes':json.loads(r['scopes'])} for r in rows if 'session' not in json.loads(r['scopes'])]

    @router.delete('/tokens/{token_id}')
    def revoke(request:Request,token_id:str):
        user=principal(request,session_only=True)
        with store.connect(True) as db:
            db.execute('DELETE FROM credentials WHERE user_id=? AND hash=?',(user['id'],token_id))
        return {'ok':True}

    return router
