"""Explicit release fixture: redirect only synthetic Cloudflare/Telegram calls."""
import urllib.request
_original=urllib.request.OpenerDirector.open
def fixture_open(self,fullurl,data=None,timeout=None):
    request=fullurl if isinstance(fullurl,urllib.request.Request) else urllib.request.Request(fullurl)
    if request.full_url.startswith('https://api.cloudflare.com/client/v4/'):
        target='http://127.0.0.1:14000/cf/'+request.full_url.split('/client/v4/',1)[1]
        request=urllib.request.Request(target,data=request.data,headers=dict(request.header_items()),method=request.get_method())
        return _original(self,request,data,timeout=timeout)
    if request.full_url=='https://api.telegram.org/bot123456789:synthetic_release_telegram_token_only/sendMessage':
        request=urllib.request.Request('http://127.0.0.1:14000/telegram/sendMessage',data=request.data,headers=dict(request.header_items()),method=request.get_method())
        return _original(self,request,data,timeout=timeout)
    return _original(self,fullurl,data,timeout=timeout)
urllib.request.OpenerDirector.open=fixture_open
