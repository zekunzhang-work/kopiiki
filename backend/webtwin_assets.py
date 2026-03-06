import requests
from bs4 import BeautifulSoup
import os
import re
import json
from urllib.parse import urljoin, urlparse, urlunparse, unquote, quote, parse_qs
import zipfile
import cssutils
import logging
import uuid
import random
import time
import urllib3
import tempfile
from datetime import datetime
import traceback
import html

# ── Logging ──────────────────────────────────────────────
logger = logging.getLogger('kopiiki.assets')
cssutils.log.setLevel(logging.CRITICAL)   # suppress noisy cssutils warnings

# ── Constants ────────────────────────────────────────────
USER_AGENTS = [
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
]


def is_binary_content(content, asset_type):
    """Determine if content should be treated as binary or text based on asset type and content inspection"""
    if asset_type in ['images', 'fonts', 'videos', 'audio']:
        return True
    if asset_type in ['css', 'js', 'html', 'svg', 'json', 'globals_css']:
        if not isinstance(content, bytes):
            return False
        try:
            if b'\x00' in content:
                return True
            sample = content[:1024]
            text_chars = bytearray({7, 8, 9, 10, 12, 13, 27} | set(range(32, 256)) - {127})
            return bool(sample.translate(None, text_chars))
        except:
            return True
    return isinstance(content, bytes)

def download_asset(url, base_url, headers=None, session_obj=None):
    """
    Download an asset from a URL
    
    Args:
        url: URL to download from
        base_url: Base URL of the website (for referrer)
        headers: Optional custom headers
        session_obj: Optional requests.Session object for maintaining cookies
    
    Returns:
        Content of the asset or None if download failed
    """
    random_user_agent = random.choice(USER_AGENTS)
    if not headers:
        headers = {'User-Agent': random_user_agent, 'Accept': '*/*', 'Accept-Language': 'en-US,en;q=0.9', 'Accept-Encoding': 'gzip, deflate, br', 'Connection': 'keep-alive', 'Referer': base_url, 'Sec-Fetch-Dest': 'empty', 'Sec-Fetch-Mode': 'cors', 'Sec-Fetch-Site': 'same-origin', 'Pragma': 'no-cache', 'Cache-Control': 'no-cache'}
    else:
        headers['User-Agent'] = random_user_agent
    try:
        parsed_url = urlparse(url)
        if not parsed_url.scheme or not parsed_url.netloc:
            logger.warning(f'Invalid URL: {url}')
            return None
    except Exception as e:
        logger.error(f'Error parsing URL {url}: {str(e)}')
        return None
    time.sleep(0.1)
    max_retries = 3
    retry_count = 0
    while retry_count < max_retries:
        try:
            if session_obj:
                response = session_obj.get(url, timeout=15, headers=headers, stream=True, allow_redirects=True, verify=False)
            else:
                response = requests.get(url, timeout=15, headers=headers, stream=True, allow_redirects=True, verify=False)
            if response.history:
                logger.debug(f'Request for {url} was redirected {len(response.history)} times to {response.url}')
                url = response.url
            if response.status_code == 200:
                content_type = response.headers.get('Content-Type', '')
                logger.debug(f'Downloaded {url} ({len(response.content)} bytes, type: {content_type})')
                is_binary = any((binary_type in content_type.lower() for binary_type in ['image/', 'video/', 'audio/', 'font/', 'application/octet-stream', 'application/zip', 'application/x-rar', 'application/pdf', 'application/vnd.']))
                if is_binary:
                    return response.content
                is_text = any((text_type in content_type.lower() for text_type in ['text/', 'application/json', 'application/javascript', 'application/xml', 'application/xhtml']))
                if is_text:
                    encoding = None
                    if 'charset=' in content_type:
                        encoding = content_type.split('charset=')[1].split(';')[0].strip()
                    if not encoding:
                        encoding = response.encoding or response.apparent_encoding or 'utf-8'
                    try:
                        return response.content.decode(encoding, errors='replace').encode('utf-8')
                    except (UnicodeDecodeError, LookupError):
                        try:
                            return response.content.decode('utf-8', errors='replace').encode('utf-8')
                        except:
                            return response.content
                return response.content
            elif response.status_code == 404:
                logger.debug(f'Resource not found (404): {url}')
                return None
            elif response.status_code == 403:
                logger.warning(f'Access forbidden (403): {url}')
                headers['User-Agent'] = random.choice(USER_AGENTS)
                retry_count += 1
                time.sleep(1)
                continue
            elif response.status_code >= 500:
                logger.error(f'Server error ({response.status_code}): {url}')
                retry_count += 1
                time.sleep(1)
                continue
            else:
                logger.error(f'HTTP error ({response.status_code}): {url}')
                return None
        except requests.exceptions.Timeout:
            logger.error(f'Timeout error downloading {url}')
            retry_count += 1
            time.sleep(1)
            continue
        except requests.exceptions.ConnectionError:
            logger.error(f'Connection error downloading {url}')
            retry_count += 1
            time.sleep(1)
            continue
        except requests.exceptions.TooManyRedirects:
            logger.warning(f'Too many redirects for {url}')
            return None
        except Exception as e:
            logger.error(f'Error downloading {url}: {str(e)}')
            return None
    if retry_count == max_retries:
        logger.warning(f'Max retries reached for {url}')
    return None

def get_asset_type(url):
    """Determine the type of asset from the URL"""
    if not url:
        return 'other'
    url_lower = url.lower()
    if '_next/static' in url_lower:
        if '.css' in url_lower or 'styles' in url_lower:
            return 'css'
        return 'js'
    if 'chunk.' in url_lower or 'webpack' in url_lower:
        return 'js'
    if 'angular' in url_lower and '.js' in url_lower:
        return 'js'
    if url_lower.endswith(('.css', '.scss', '.less', '.sass')):
        return 'css'
    if 'global.css' in url_lower or 'globals.css' in url_lower or 'tailwind' in url_lower:
        return 'css'
    if 'fonts.googleapis.com' in url_lower:
        return 'css'
    if 'styles' in url_lower and '.css' in url_lower:
        return 'css'
    if url_lower.endswith(('.js', '.jsx', '.mjs', '.ts', '.tsx', '.cjs')):
        return 'js'
    if 'bundle.js' in url_lower or 'main.js' in url_lower or 'app.js' in url_lower:
        return 'js'
    if 'polyfill' in url_lower or 'runtime' in url_lower or 'vendor' in url_lower:
        return 'js'
    if 'image-config' in url_lower or 'image.config' in url_lower:
        return 'js'
    if url_lower.endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.avif', '.bmp', '.ico')):
        return 'img'
    if '/images/' in url_lower or '/img/' in url_lower or '/assets/images/' in url_lower:
        return 'img'
    if url_lower.endswith(('.woff', '.woff2', '.ttf', '.otf', '.eot')):
        return 'fonts'
    if '/fonts/' in url_lower or 'font-awesome' in url_lower:
        return 'fonts'
    if url_lower.endswith(('.mp4', '.webm', '.ogg', '.avi', '.mov', '.flv')):
        return 'videos'
    if url_lower.endswith(('.mp3', '.wav', '.ogg', '.aac')):
        return 'audio'
    if url_lower.endswith(('.ico', '.icon')):
        return 'favicons'
    if 'favicon' in url_lower:
        return 'favicons'
    if 'graphql' in url_lower or 'api.' in url_lower:
        return 'js'
    if '/css/' in url_lower:
        return 'css'
    if '/js/' in url_lower or '/scripts/' in url_lower:
        return 'js'
    if '/static/' in url_lower and (not any((ext in url_lower for ext in ['.css', '.js', '.png', '.jpg']))):
        if 'style' in url_lower:
            return 'css'
        return 'js'
    cdn_hosts = ['cdn.jsdelivr.net', 'unpkg.com', 'cdnjs.cloudflare.com']
    for host in cdn_hosts:
        if host in url_lower:
            if any((lib in url_lower for lib in ['react', 'angular', 'vue', 'jquery'])):
                return 'js'
            if any((lib in url_lower for lib in ['bootstrap', 'tailwind', 'material', 'font'])):
                return 'css'
    return 'js'

def extract_metadata(soup, base_url):
    """Extract metadata from the HTML"""
    metadata = {'title': '', 'description': '', 'keywords': '', 'og_tags': {}, 'twitter_cards': {}, 'canonical': '', 'language': '', 'favicon': '', 'structured_data': []}
    title_tag = soup.find('title')
    if title_tag and title_tag.string:
        metadata['title'] = title_tag.string.strip()
    meta_tags = soup.find_all('meta')
    for tag in meta_tags:
        if tag.get('name') == 'description' and tag.get('content'):
            metadata['description'] = tag.get('content').strip()
        elif tag.get('name') == 'keywords' and tag.get('content'):
            metadata['keywords'] = tag.get('content').strip()
        elif tag.get('property') and tag.get('property').startswith('og:') and tag.get('content'):
            prop = tag.get('property')[3:]
            metadata['og_tags'][prop] = tag.get('content').strip()
        elif tag.get('name') and tag.get('name').startswith('twitter:') and tag.get('content'):
            prop = tag.get('name')[8:]
            metadata['twitter_cards'][prop] = tag.get('content').strip()
    canonical_tag = soup.find('link', {'rel': 'canonical'})
    if canonical_tag and canonical_tag.get('href'):
        canonical_url = canonical_tag.get('href')
        if not canonical_url.startswith(('http://', 'https://')):
            canonical_url = urljoin(base_url, canonical_url)
        metadata['canonical'] = canonical_url
    html_tag = soup.find('html')
    if html_tag and html_tag.get('lang'):
        metadata['language'] = html_tag.get('lang')
    favicon_tag = soup.find('link', {'rel': 'icon'}) or soup.find('link', {'rel': 'shortcut icon'})
    if favicon_tag and favicon_tag.get('href'):
        favicon_url = favicon_tag.get('href')
        if not favicon_url.startswith(('http://', 'https://')):
            favicon_url = urljoin(base_url, favicon_url)
        metadata['favicon'] = favicon_url
    script_tags = soup.find_all('script', {'type': 'application/ld+json'})
    for tag in script_tags:
        if tag.string:
            try:
                json_data = json.loads(tag.string)
                metadata['structured_data'].append(json_data)
            except json.JSONDecodeError:
                pass
    return metadata

def get_component_type(element):
    """Determine the type of UI component based on element attributes and classes"""
    if not element:
        return None
    tag_name = element.name
    class_list = element.get('class', [])
    if class_list and (not isinstance(class_list, list)):
        class_list = [class_list]
    class_str = ' '.join(class_list).lower() if class_list else ''
    element_id = element.get('id', '').lower()
    role = element.get('role', '').lower()
    if tag_name == 'nav' or role == 'navigation' or 'nav' in class_str or ('navigation' in class_str) or ('menu' in class_str) or (element_id in ['nav', 'navigation', 'menu']):
        return 'navigation'
    if tag_name == 'header' or role == 'banner' or 'header' in class_str or ('banner' in class_str) or (element_id in ['header', 'banner']):
        return 'header'
    if tag_name == 'footer' or role == 'contentinfo' or 'footer' in class_str or (element_id == 'footer'):
        return 'footer'
    if 'hero' in class_str or 'banner' in class_str or 'jumbotron' in class_str or ('showcase' in class_str) or (element_id in ['hero', 'banner', 'jumbotron', 'showcase']):
        return 'hero'
    if 'card' in class_str or 'tile' in class_str or 'item' in class_str or (element_id in ['card', 'tile']):
        return 'card'
    if tag_name == 'form' or role == 'form' or 'form' in class_str or (element_id == 'form'):
        return 'form'
    if 'cta' in class_str or 'call-to-action' in class_str or 'action' in class_str or (element_id in ['cta', 'call-to-action']):
        return 'cta'
    if 'sidebar' in class_str or 'side-bar' in class_str or element_id in ['sidebar', 'side-bar']:
        return 'sidebar'
    if role == 'dialog' or 'modal' in class_str or 'dialog' in class_str or ('popup' in class_str) or (element_id in ['modal', 'dialog', 'popup']):
        return 'modal'
    if tag_name == 'section' or role == 'region' or 'section' in class_str:
        return 'section'
    if 'mobile' in class_str or 'smartphone' in class_str or 'mobile-only' in class_str:
        return 'mobile'
    if 'product' in class_str or 'store' in class_str or 'shop' in class_str or ('pricing' in class_str):
        return 'store'
    if 'cart' in class_str or 'basket' in class_str or 'shopping-cart' in class_str or (element_id in ['cart', 'basket', 'shopping-cart']):
        return 'cart'
    if tag_name in ['div', 'section', 'article'] and ('container' in class_str or 'wrapper' in class_str or 'content' in class_str):
        return 'container'
    return 'other'

def extract_component_structure(soup):
    """Extract UI components from the HTML structure"""
    if not soup:
        return {}
    components = {'navigation': [], 'header': [], 'footer': [], 'hero': [], 'card': [], 'form': [], 'cta': [], 'sidebar': [], 'modal': [], 'section': [], 'store': [], 'mobile': [], 'cart': []}

    def element_to_html(element):
        return str(element)
    nav_elements = soup.find_all(['nav']) + soup.find_all(role='navigation') + soup.find_all(class_=lambda c: c and ('nav' in c.lower() or 'menu' in c.lower()))
    for element in nav_elements[:5]:
        components['navigation'].append({'html': element_to_html(element)})
    header_elements = soup.find_all(['header']) + soup.find_all(role='banner') + soup.find_all(class_=lambda c: c and 'header' in c.lower())
    for element in header_elements[:2]:
        components['header'].append({'html': element_to_html(element)})
    footer_elements = soup.find_all(['footer']) + soup.find_all(role='contentinfo') + soup.find_all(class_=lambda c: c and 'footer' in c.lower())
    for element in footer_elements[:2]:
        components['footer'].append({'html': element_to_html(element)})
    hero_elements = soup.find_all(class_=lambda c: c and ('hero' in c.lower() or 'banner' in c.lower() or 'jumbotron' in c.lower()))
    for element in hero_elements[:3]:
        components['hero'].append({'html': element_to_html(element)})
    card_elements = soup.find_all(class_=lambda c: c and ('card' in c.lower() or 'tile' in c.lower()))
    unique_cards = {}
    for element in card_elements[:15]:
        structure_hash = str(len(element.find_all()))
        if structure_hash not in unique_cards:
            unique_cards[structure_hash] = element
    for (idx, element) in enumerate(unique_cards.values()):
        if idx >= 5:
            break
        components['card'].append({'html': element_to_html(element)})
    form_elements = soup.find_all(['form']) + soup.find_all(class_=lambda c: c and 'form' in c.lower())
    for element in form_elements[:3]:
        components['form'].append({'html': element_to_html(element)})
    cta_elements = soup.find_all(class_=lambda c: c and ('cta' in c.lower() or 'call-to-action' in c.lower()))
    for element in cta_elements[:3]:
        components['cta'].append({'html': element_to_html(element)})
    sidebar_elements = soup.find_all(class_=lambda c: c and ('sidebar' in c.lower() or 'side-bar' in c.lower()))
    for element in sidebar_elements[:2]:
        components['sidebar'].append({'html': element_to_html(element)})
    modal_elements = soup.find_all(role='dialog') + soup.find_all(class_=lambda c: c and ('modal' in c.lower() or 'dialog' in c.lower() or 'popup' in c.lower()))
    for element in modal_elements[:3]:
        components['modal'].append({'html': element_to_html(element)})
    section_elements = soup.find_all(['section']) + soup.find_all(role='region')
    substantial_sections = [element for element in section_elements if len(element.find_all()) > 3]
    for element in substantial_sections[:5]:
        components['section'].append({'html': element_to_html(element)})
    mobile_elements = soup.find_all(class_=lambda c: c and ('mobile' in c.lower() or 'smartphone' in c.lower() or 'mobile-only' in c.lower()))
    for element in mobile_elements[:3]:
        components['mobile'].append({'html': element_to_html(element)})
    store_elements = soup.find_all(class_=lambda c: c and ('product' in c.lower() or 'store' in c.lower() or 'shop' in c.lower() or ('pricing' in c.lower())))
    for element in store_elements[:5]:
        components['store'].append({'html': element_to_html(element)})
    cart_elements = soup.find_all(class_=lambda c: c and ('cart' in c.lower() or 'basket' in c.lower() or 'shopping-cart' in c.lower()))
    for element in cart_elements[:2]:
        components['cart'].append({'html': element_to_html(element)})
    return {k: v for (k, v) in components.items() if v}

def extract_inline_styles(soup):
    """Extract all inline styles from the HTML"""
    inline_styles = {}
    elements_with_style = soup.select('[style]')
    for (i, element) in enumerate(elements_with_style):
        style_content = element.get('style')
        if style_content:
            class_name = f'extracted-inline-style-{i}'
            inline_styles[class_name] = style_content
            element['class'] = element.get('class', []) + [class_name]
            del element['style']
    return inline_styles

def extract_inline_javascript(soup):
    """Extract inline JavaScript from HTML content"""
    inline_js = []
    for script in soup.find_all('script'):
        if not script.get('src') and script.string:
            inline_js.append(script.string.strip())
    if inline_js:
        return '\n\n/* --- INLINE SCRIPTS --- */\n\n'.join(inline_js)
    return ''

def extract_assets(html_content, base_url, session_obj=None, headers=None):
    """Extract all assets from HTML content"""
    assets = {'css': [], 'js': [], 'img': [], 'fonts': [], 'videos': [], 'audio': [], 'favicons': [], 'font_families': set(), 'metadata': {}, 'components': {}}
    if not html_content:
        logger.warning('Warning: Empty HTML content provided to extract_assets')
        return assets
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        if not soup or not soup.html:
            logger.warning('Warning: Could not parse HTML content properly')
            soup = BeautifulSoup(html_content, 'html5lib')
            if not soup or not soup.html:
                logger.error('Error: Failed to parse HTML with both parsers')
                return assets
        try:
            assets['metadata'] = extract_metadata(soup, base_url)
        except Exception as e:
            logger.error(f'Error extracting metadata: {str(e)}')
            traceback.print_exc()
        try:
            css_links = soup.find_all('link', {'rel': 'stylesheet'}) or []
            preload_css = soup.find_all('link', {'rel': 'preload', 'as': 'style'}) or []
            for link in css_links + preload_css:
                href = link.get('href')
                if href:
                    if not href.startswith(('http://', 'https://', 'data:')):
                        href = urljoin(base_url, href)
                    if href.startswith(('http://', 'https://')):
                        assets['css'].append(href)
        except Exception as e:
            logger.error(f'Error extracting CSS links: {str(e)}')
        try:
            next_css = soup.find_all('link', {'data-n-g': True}) or []
            next_css += soup.find_all('link', {'data-n-p': True}) or []
            for link in next_css:
                href = link.get('href')
                if href:
                    if not href.startswith(('http://', 'https://', 'data:')):
                        href = urljoin(base_url, href)
                    if href.startswith(('http://', 'https://')):
                        assets['css'].append(href)
        except Exception as e:
            logger.error(f'Error extracting Next.js CSS: {str(e)}')
        try:
            style_tags = soup.find_all('style') or []
            for style in style_tags:
                style_content = style.string
                if style_content:
                    import_urls = re.findall('@import\\s+[\\\'"]([^\\\'"]+)[\\\'"]', style_content) or []
                    import_urls += re.findall('@import\\s+url\\([\\\'"]?([^\\\'"|\\)]+)[\\\'"]?\\)', style_content) or []
                    for import_url in import_urls:
                        if not import_url.startswith(('http://', 'https://', 'data:')):
                            import_url = urljoin(base_url, import_url)
                        if import_url.startswith(('http://', 'https://')):
                            assets['css'].append(import_url)
                    font_families = re.findall('font-family:\\s*[\\\'"]?([^\\\'";]+)[\\\'"]?', style_content) or []
                    for family in font_families:
                        family = family.strip().split(',')[0].strip('\'"`')
                        if family and family.lower() not in ['serif', 'sans-serif', 'monospace', 'cursive', 'fantasy', 'system-ui']:
                            assets['font_families'].add(family)
        except Exception as e:
            logger.error(f'Error extracting inline styles: {str(e)}')
        try:
            script_tags = soup.find_all('script', {'src': True}) or []
            for script in script_tags:
                src = script.get('src')
                if src:
                    if not src.startswith(('http://', 'https://', 'data:')):
                        src = urljoin(base_url, src)
                    if src.startswith(('http://', 'https://')):
                        assets['js'].append(src)
            module_scripts = soup.find_all('script', {'type': 'module'}) or []
            for script in module_scripts:
                src = script.get('src')
                if src:
                    if not src.startswith(('http://', 'https://', 'data:')):
                        src = urljoin(base_url, src)
                    if src.startswith(('http://', 'https://')):
                        assets['js'].append(src)
        except Exception as e:
            logger.error(f'Error extracting JavaScript: {str(e)}')
        try:
            img_tags = soup.find_all('img') or []
            for img in img_tags:
                src = img.get('src')
                if src:
                    if not src.startswith(('http://', 'https://', 'data:')):
                        src = urljoin(base_url, src)
                    if src.startswith(('http://', 'https://')):
                        assets['img'].append(src)
                srcset = img.get('srcset')
                if srcset:
                    for src_str in srcset.split(','):
                        src_parts = src_str.strip().split(' ')
                        if src_parts:
                            src = src_parts[0]
                            if not src.startswith(('http://', 'https://', 'data:')):
                                src = urljoin(base_url, src)
                            if src.startswith(('http://', 'https://')):
                                assets['img'].append(src)
                data_src = img.get('data-src')
                if data_src:
                    if not data_src.startswith(('http://', 'https://', 'data:')):
                        data_src = urljoin(base_url, data_src)
                    if data_src.startswith(('http://', 'https://')):
                        assets['img'].append(data_src)
            elements_with_style = soup.select('[style]') or []
            for element in elements_with_style:
                style = element.get('style', '')
                if 'background' in style or 'background-image' in style:
                    bg_urls = re.findall('url\\([\\\'"]?([^\\\'"|\\)]+)[\\\'"]?\\)', style)
                    for bg_url in bg_urls:
                        if not bg_url.startswith(('http://', 'https://', 'data:')):
                            bg_url = urljoin(base_url, bg_url)
                        if bg_url.startswith(('http://', 'https://')):
                            assets['img'].append(bg_url)
        except Exception as e:
            logger.error(f'Error extracting images: {str(e)}')
        try:
            favicon_links = soup.find_all('link', {'rel': lambda r: r and (r.lower() == 'icon' or 'icon' in r.lower().split())}) or []
            for link in favicon_links:
                href = link.get('href')
                if href:
                    if not href.startswith(('http://', 'https://', 'data:')):
                        href = urljoin(base_url, href)
                    if href.startswith(('http://', 'https://')):
                        assets['favicons'].append(href)
        except Exception as e:
            logger.error(f'Error extracting favicons: {str(e)}')
        try:
            video_tags = soup.find_all('video') or []
            for video in video_tags:
                src = video.get('src')
                if src:
                    if not src.startswith(('http://', 'https://', 'data:')):
                        src = urljoin(base_url, src)
                    if src.startswith(('http://', 'https://')):
                        assets['videos'].append(src)
                source_tags = video.find_all('source') or []
                for source in source_tags:
                    src = source.get('src')
                    if src:
                        if not src.startswith(('http://', 'https://', 'data:')):
                            src = urljoin(base_url, src)
                        if src.startswith(('http://', 'https://')):
                            assets['videos'].append(src)
        except Exception as e:
            logger.error(f'Error extracting videos: {str(e)}')
        try:
            audio_tags = soup.find_all('audio') or []
            for audio in audio_tags:
                src = audio.get('src')
                if src:
                    if not src.startswith(('http://', 'https://', 'data:')):
                        src = urljoin(base_url, src)
                    if src.startswith(('http://', 'https://')):
                        assets['audio'].append(src)
                source_tags = audio.find_all('source') or []
                for source in source_tags:
                    src = source.get('src')
                    if src:
                        if not src.startswith(('http://', 'https://', 'data:')):
                            src = urljoin(base_url, src)
                        if src.startswith(('http://', 'https://')):
                            assets['audio'].append(src)
        except Exception as e:
            logger.error(f'Error extracting audio: {str(e)}')
        try:
            iframe_tags = soup.find_all('iframe') or []
            for iframe in iframe_tags:
                src = iframe.get('src')
                if src and (not src.startswith('data:')):
                    if not src.startswith(('http://', 'https://')):
                        src = urljoin(base_url, src)
                    if src.startswith(('http://', 'https://')):
                        if 'youtube' in src or 'vimeo' in src:
                            assets['videos'].append(src)
                        else:
                            assets['js'].append(src)
        except Exception as e:
            logger.error(f'Error extracting iframes: {str(e)}')
        try:
            next_data = soup.find('script', {'id': '__NEXT_DATA__'})
            if next_data and next_data.string:
                try:
                    next_json = json.loads(next_data.string)
                    if 'buildId' in next_json:
                        build_id = next_json['buildId']
                        for path in ['main', 'webpack', 'framework', 'pages/_app', 'pages/_error', 'pages/index']:
                            chunk_url = f'{base_url}/_next/static/{build_id}/pages/{path}.js'
                            assets['js'].append(chunk_url)
                    if 'page' in next_json and 'props' in next_json.get('props', {}):
                        assets['metadata']['next_data'] = next_json
                except Exception as next_error:
                    logger.error(f'Error parsing Next.js data: {str(next_error)}')
            chunks_regex = '/\\*\\s*webpackJsonp\\s*\\*/(.*?)/\\*\\s*end\\s*webpackJsonp\\s*\\*/'
            chunks_matches = re.findall(chunks_regex, html_content, re.DOTALL)
            if chunks_matches:
                logger.info('Found webpack chunks in comments')
        except Exception as e:
            logger.error(f'Error extracting Next.js resources: {str(e)}')
        if session_obj and headers:
            try:
                css_urls = assets['css'].copy()
                for css_url in css_urls:
                    try:
                        if css_url.startswith('data:'):
                            continue
                        response = session_obj.get(css_url, timeout=10, headers=headers, verify=False)
                        if response.status_code == 200:
                            css_content = response.text
                            url_matches = re.findall('url\\([\\\'"]?([^\\\'"|\\)]+)[\\\'"]?\\)', css_content) or []
                            for url in url_matches:
                                if not url or url.startswith('data:'):
                                    continue
                                if not url.startswith(('http://', 'https://')):
                                    url = urljoin(css_url, url)
                                asset_type = get_asset_type(url)
                                if asset_type in assets:
                                    assets[asset_type].append(url)
                            font_families = re.findall('font-family:\\s*[\\\'"]?([^\\\'";]+)[\\\'"]?', css_content) or []
                            for family in font_families:
                                family = family.strip().split(',')[0].strip('\'"`')
                                if family and family.lower() not in ['serif', 'sans-serif', 'monospace', 'cursive', 'fantasy', 'system-ui']:
                                    assets['font_families'].add(family)
                            google_fonts_imports = re.findall('@import\\s+url\\([\\\'"]?(https?://fonts\\.googleapis\\.com/[^\\\'"|\\)]+)[\\\'"]?\\)', css_content) or []
                            for font_url in google_fonts_imports:
                                if font_url not in assets['css']:
                                    assets['css'].append(font_url)
                            if 'tailwind' in css_content.lower() or '.tw-' in css_content:
                                logger.info('Detected Tailwind CSS in stylesheets')
                    except Exception as css_error:
                        logger.error(f'Error processing CSS {css_url}: {str(css_error)}')
            except Exception as e:
                logger.error(f'Error processing CSS files: {str(e)}')
        try:
            components = extract_component_structure(soup)
            if components:
                assets['components'] = components
        except Exception as e:
            logger.error(f'Error extracting components: {str(e)}')
            traceback.print_exc()
        for asset_type in assets:
            if isinstance(assets[asset_type], list):
                assets[asset_type] = list(dict.fromkeys(assets[asset_type]))
        return assets
    except Exception as e:
        logger.error(f'Error in extract_assets: {str(e)}')
        traceback.print_exc()
        return assets

def create_zip_file(html_content, assets, url, session_obj, headers, screenshots=None):
    """Create a zip file containing the extracted website data"""
    temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
    temp_zip.close()
    parsed_url = urlparse(url)
    domain = parsed_url.netloc
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    with zipfile.ZipFile(temp_zip.name, 'w', zipfile.ZIP_DEFLATED) as zipf:
        zipf.writestr('index.html', html_content)
        for asset_type in assets.keys():
            if asset_type in ['font_families', 'metadata', 'components']:
                continue
            if not assets[asset_type] or not isinstance(assets[asset_type], list):
                logger.debug(f'  Skipping {asset_type} - no assets found or invalid format')
                continue
            zipf.writestr(f'{asset_type}/.gitkeep', '')
            processed_urls = set()
            filename_counter = {}  # Track duplicate filenames
            for url in assets[asset_type]:
                if not url or url.startswith('data:'):
                    continue
                if url in processed_urls:
                    continue
                processed_urls.add(url)
                try:
                    if url.startswith('//'):
                        url = 'https:' + url
                    elif url.startswith('/'):
                        parsed_base = urlparse(parsed_url.scheme + '://' + parsed_url.netloc)
                        url = urljoin(parsed_base.geturl(), url)

                    parsed_asset = urlparse(url)
                    path = parsed_asset.path
                    filename = os.path.basename(unquote(path))

                    # Fallback for empty filenames
                    if not filename:
                        filename = f'{uuid.uuid4().hex[:8]}'

                    # Split name and extension
                    name, ext = os.path.splitext(filename)

                    # Infer extension from asset_type if missing
                    if not ext:
                        ext_map = {
                            'css': '.css', 'js': '.js', 'images': '.png',
                            'fonts': '.woff2', 'favicons': '.ico',
                            'videos': '.mp4', 'audio': '.mp3',
                        }
                        ext = ext_map.get(asset_type, '')

                    # Clean the name: keep alphanumeric, hyphens, underscores
                    name = re.sub(r'[^a-zA-Z0-9._\-]', '_', name)
                    # Remove consecutive underscores
                    name = re.sub(r'_+', '_', name).strip('_')

                    # Truncate name to keep total filename readable (max 60 chars)
                    max_name_len = 60 - len(ext)
                    if len(name) > max_name_len:
                        name = name[:max_name_len].rstrip('_')

                    filename = f'{name}{ext}'

                    # Deduplicate: append counter if filename already seen
                    if filename in filename_counter:
                        filename_counter[filename] += 1
                        filename = f'{name}_{filename_counter[filename]}{ext}'
                    else:
                        filename_counter[filename] = 0

                    file_path = f'{asset_type}/{filename}'
                    try:
                        response = session_obj.get(url, timeout=10, headers=headers, verify=False)
                        if response.status_code == 200:
                            zipf.writestr(file_path, response.content)
                            logger.debug(f'Added {file_path}')
                        else:
                            logger.warning(f'Failed to download {url}, status: {response.status_code}')
                    except Exception as e:
                        logger.error(f'Error downloading {url}: {str(e)}')
                except Exception as e:
                    logger.error(f'Error processing URL {url}: {str(e)}')
        if 'font_families' in assets and assets['font_families']:
            zipf.writestr('css/fonts.css', '\n'.join([f"/* Font Family: {family} */\n@import url('https://fonts.googleapis.com/css2?family={family.replace(' ', '+')}&display=swap');\n" for family in assets['font_families']]))
        if 'metadata' in assets and assets['metadata']:
            metadata_content = json.dumps(assets['metadata'], indent=2)
            zipf.writestr('metadata.json', metadata_content)
        if 'components' in assets and assets['components'] and isinstance(assets['components'], dict):
            zipf.writestr('components/.gitkeep', '')
            component_html = '\n            <!DOCTYPE html>\n            <html lang="en">\n            <head>\n                <meta charset="UTF-8">\n                <meta name="viewport" content="width=device-width, initial-scale=1.0">\n                <title>Extracted UI Components</title>\n                <style>\n                    body { font-family: Arial, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; }\n                    .component { margin-bottom: 40px; border: 1px solid #ddd; border-radius: 5px; overflow: hidden; }\n                    .component-header { background: #f5f5f5; padding: 10px 15px; border-bottom: 1px solid #ddd; }\n                    .component-content { padding: 15px; }\n                    .component-code { background: #f8f8f8; padding: 15px; border-top: 1px solid #ddd; white-space: pre-wrap; overflow-x: auto; }\n                    h1, h2 { color: #333; }\n                    pre { margin: 0; }\n                </style>\n            </head>\n            <body>\n                <h1>Extracted UI Components</h1>\n                <p>The following components were extracted from the website.</p>\n            '
            for (component_type, components) in assets['components'].items():
                if components:
                    component_html += f"<h2>{component_type.replace('_', ' ').title()} Components</h2>"
                    for (i, component) in enumerate(components):
                        html_code = component.get('html', '')
                        if html_code:
                            component_html += f"""\n                            <div class="component">\n                                <div class="component-header">\n                                    <strong>{component_type.replace('_', ' ').title()} {i + 1}</strong>\n                                </div>\n                                <div class="component-content">\n                                    {html_code}\n                                </div>\n                                <div class="component-code">\n                                    <pre>{html.escape(html_code)}</pre>\n                                </div>\n                            </div>\n                            """
            component_html += '\n            </body>\n            </html>\n            '
            zipf.writestr('components/index.html', component_html)
            for (component_type, components) in assets['components'].items():
                if components:
                    zipf.writestr(f'components/{component_type}/.gitkeep', '')
                    for (i, component) in enumerate(components):
                        html_code = component.get('html', '')
                        if html_code:
                            zipf.writestr(f'components/{component_type}/component_{i + 1}.html', html_code)
        readme_content = f"# Website Clone: {domain}\n\nExtracted on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\nSource URL: {url}\n\n## Contents\n\n- `index.html`: Main HTML file\n- `css/`: Stylesheets\n- `js/`: JavaScript files\n- `img/`: Images\n- `fonts/`: Font files\n- `components/`: Extracted UI components\n- `metadata.json`: Website metadata (title, description, etc.)\n\n## How to Use\n\n1. Unzip this file\n2. Open `index.html` in your browser\n3. For best results, serve the files with a local server:\n   ```\n   python -m http.server\n   ```\n   Then open http://localhost:8000 in your browser\n\n## Component Viewer\n\nIf components were extracted, you can view them by opening `components/index.html`\n\n## Notes\n\n- Some assets might not load correctly due to cross-origin restrictions\n- External resources and APIs may not work without proper configuration\n- JavaScript functionality might be limited without a proper backend\n\n## Handling Modern Frameworks\n\nThis extraction has been optimized to handle the following frameworks:\n- React and Next.js: Script chunks and module loading\n- Angular: Component structure and scripts\n- Tailwind CSS: Utility classes and structure\n\nGenerated by Website Extractor\n"
        zipf.writestr('README.md', readme_content)
    return temp_zip.name

def fix_relative_urls(html_content, base_url):
    """Fix relative URLs in the HTML content"""
    soup = BeautifulSoup(html_content, 'html.parser')
    for link in soup.find_all('a', href=True):
        href = link['href']
        if href.startswith('/'):
            link['href'] = urljoin(base_url, href)
    for img in soup.find_all('img', src=True):
        src = img['src']
        if not src.startswith(('http://', 'https://', 'data:')):
            img['src'] = urljoin(base_url, src)
    for script in soup.find_all('script', src=True):
        src = script['src']
        if not src.startswith(('http://', 'https://', 'data:')):
            script['src'] = urljoin(base_url, src)
    for link in soup.find_all('link', href=True):
        href = link['href']
        if not href.startswith(('http://', 'https://', 'data:')):
            link['href'] = urljoin(base_url, href)
    return str(soup)

