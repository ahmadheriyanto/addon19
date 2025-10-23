from odoo import http
from odoo.http import request, Response
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

class WebsiteProxy(http.Controller):

    @http.route('/', type='http', auth='public', website=True)
    def root_proxy(self, **kwargs):
        remote = "https://www.sainslogistik.com/"
        try:
            r = requests.get(remote, timeout=10)
            r.raise_for_status()
            html = r.text
        except Exception as e:
            # fallback to default homepage or a friendly error
            return request.render('website.homepage')

        # rewrite relative links to absolute so assets load from the remote host
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all(['a', 'img', 'script', 'link', 'form']):
            # change href/src/action to absolute URLs
            if tag.name == 'a' and tag.has_attr('href'):
                tag['href'] = urljoin(remote, tag['href'])
            if tag.name == 'img' and tag.has_attr('src'):
                tag['src'] = urljoin(remote, tag['src'])
            if tag.name == 'script' and tag.has_attr('src'):
                tag['src'] = urljoin(remote, tag['src'])
            if tag.name == 'link' and tag.has_attr('href'):
                tag['href'] = urljoin(remote, tag['href'])
            if tag.name == 'form' and tag.has_attr('action'):
                tag['action'] = urljoin(remote, tag['action'])

        # Optionally inject a small banner or edit anything
        # return the proxied HTML directly
        return Response(str(soup), headers=[('Content-Type', 'text/html')])