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

def extract_assets(html_content, base_url, session_obj=None, headers=None, captured_assets=None):
    """Extract all assets from HTML content"""
    if captured_assets is None:
        captured_assets = {}
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
                        css_content = None # Fixed leak
                        response = session_obj.get(css_url, timeout=10, headers=headers, verify=False)
                        if response.status_code == 200:
                            css_content = response.text
                        elif css_url in captured_assets:
                            css_content = captured_assets[css_url].decode('utf-8', errors='replace')
                        
                        if css_content:
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


def rewrite_css_urls(css_content, url_mapping):
    """Rewrite absolute URLs in CSS to relative local paths."""
    if not css_content:
        return css_content
    css_text = css_content.decode("utf-8", errors="replace") if isinstance(css_content, bytes) else css_content
    # CSS is in 'css/' folder, so reference to 'img/xxx.png' becomes '../img/xxx.png'
    # reference to 'fonts/xxx.woff' becomes '../fonts/xxx.woff'
    # reference to 'css/xxx.css' becomes './xxx.css' 
    for original_url, local_path in url_mapping.items():
        if local_path.startswith("css/"):
            rel_path = local_path.replace("css/", "./", 1)
        else:
            rel_path = "../" + local_path
        # Very simple global string replace for the absolute URLs inside CSS
        css_text = css_text.replace(original_url, rel_path)
    return css_text.encode("utf-8", errors="replace")

def rewrite_html_dom(html_content, url_mapping):
    """Rewrite absolute URLs in HTML AST to local relative paths."""
    soup = BeautifulSoup(html_content, "html.parser")
    
    for tag in soup.find_all(["a", "link"], href=True):
        if tag["href"] in url_mapping:
            tag["href"] = "./" + url_mapping[tag["href"]]
            
    for tag in soup.find_all(["img", "script", "source", "video", "audio", "iframe"], src=True):
        if tag["src"] in url_mapping:
            tag["src"] = "./" + url_mapping[tag["src"]]
            
    # Also handle inline styles
    for tag in soup.find_all(style=True):
        style_text = tag["style"]
        modified = False
        for original_url, local_path in url_mapping.items():
            if original_url in style_text:
                style_text = style_text.replace(original_url, "./" + local_path)
                modified = True
        if modified:
            tag["style"] = style_text
            
    # Remove integrity attributes since we might modify CSS/JS
    for tag in soup.find_all(integrity=True):
        del tag["integrity"]
        
    return str(soup)

def create_zip_file(html_content, assets, url, session_obj, headers, screenshots=None, captured_assets=None):
    if captured_assets is None:
        captured_assets = {}
    temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
    temp_zip.close()
    parsed_url = urlparse(url)
    domain = parsed_url.netloc
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    url_mapping = {}  # { 'https://foo.com/bg.png': 'img/bg_123.png' }
    downloaded_buffers = {} # { 'img/bg_123.png': b'...' }
    
    # 1. Process all assets and download into memory buffers while building mapping
    for asset_type in assets.keys():
        if asset_type in ['font_families', 'metadata', 'components']:
            continue
        if not assets[asset_type] or not isinstance(assets[asset_type], list):
            continue
            
        processed_asset_urls = set()
        filename_counter = {}
        for asset_url in assets[asset_type]:
            if not asset_url or asset_url.startswith('data:'):
                continue
            if asset_url in processed_asset_urls:
                continue
            processed_asset_urls.add(asset_url)
            
            # Formatting URL
            formatted_url = asset_url
            if formatted_url.startswith('//'):
                formatted_url = 'https:' + formatted_url
            elif formatted_url.startswith('/'):
                parsed_base = urlparse(parsed_url.scheme + '://' + parsed_url.netloc)
                formatted_url = urljoin(parsed_base.geturl(), formatted_url)
                
            parsed_asset = urlparse(formatted_url)
            filename = os.path.basename(unquote(parsed_asset.path))
            if not filename:
                filename = f"{uuid.uuid4().hex[:8]}"
            name, ext = os.path.splitext(filename)
            
            if not ext:
                ext_map = {'css': '.css', 'js': '.js', 'img': '.png', 'fonts': '.woff2', 'favicons': '.ico', 'videos': '.mp4', 'audio': '.mp3'}
                ext = ext_map.get(asset_type, '')
            
            name = re.sub(r'[^a-zA-Z0-9._\-]', '_', name)
            name = re.sub(r'_+', '_', name).strip('_')
            max_name_len = 60 - len(ext)
            if len(name) > max_name_len:
                name = name[:max_name_len].rstrip('_')
            filename = f"{name}{ext}"
            
            if filename in filename_counter:
                filename_counter[filename] += 1
                filename = f"{name}_{filename_counter[filename]}{ext}"
            else:
                filename_counter[filename] = 0
                
            file_path = f"{asset_type}/{filename}"
            url_mapping[asset_url] = file_path   # Store original URL mapping to mapped path
            if formatted_url != asset_url:
                url_mapping[formatted_url] = file_path
            
            # Buffer the asset
            if formatted_url in captured_assets and captured_assets[formatted_url]:
                downloaded_buffers[file_path] = captured_assets[formatted_url]
                logger.debug(f"Buffered {file_path} from cache")
            elif asset_url in captured_assets and captured_assets[asset_url]:
                downloaded_buffers[file_path] = captured_assets[asset_url]
                logger.debug(f"Buffered {file_path} from cache")
            else:
                try:
                    response = session_obj.get(formatted_url, timeout=10, headers=headers, verify=False)
                    if response.status_code == 200:
                        downloaded_buffers[file_path] = response.content
                        logger.debug(f"Buffered {file_path} via network")
                except Exception as e:
                    logger.error(f"Error downloading {formatted_url}: {str(e)}")

    # 2. Re-write HTML DOM
    final_html = rewrite_html_dom(html_content, url_mapping)
    
    # 3. Write ZIP
    with zipfile.ZipFile(temp_zip.name, 'w', zipfile.ZIP_DEFLATED) as zipf:
        zipf.writestr('index.html', final_html)
        
        for file_path, content in downloaded_buffers.items():
            if file_path.startswith("css/"):
                content = rewrite_css_urls(content, url_mapping)
            zipf.writestr(file_path, content)
            
        for asset_type in ['css', 'js', 'img', 'fonts', 'favicons', 'videos', 'audio']:
            zipf.writestr(f'{asset_type}/.gitkeep', '')
            
        if 'font_families' in assets and assets['font_families']:
            zipf.writestr('css/fonts.css', '\n'.join([f"/* Font Family: {family} */\n@import url('https://fonts.googleapis.com/css2?family={family.replace(' ', '+')}&display=swap');\n" for family in assets['font_families']]))
        if 'metadata' in assets and assets['metadata']:
            zipf.writestr('metadata.json', json.dumps(assets['metadata'], indent=2))
        if 'components' in assets and assets['components'] and isinstance(assets['components'], dict):
            zipf.writestr('components/.gitkeep', '')
            # components structure ommitted or simplified for brevity, just keeping standard dump
            for (component_type, components) in assets['components'].items():
                if components:
                    zipf.writestr(f'components/{component_type}/.gitkeep', '')
                    for (i, component) in enumerate(components):
                        html_code = component.get('html', '')
                        if html_code:
                            zipf.writestr(f'components/{component_type}/component_{i + 1}.html', html_code)
                            
        readme_content = f"# Website Clone: {domain}\n\nExtracted on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\nSource URL: {url}\n\n## Contents\n\n- `index.html`: Main HTML file\n- `css/`: Stylesheets\n- `js/`: JavaScript files\n- `img/`: Images\n- `fonts/`: Font files\n\n## How to Use\n\n1. Unzip this file\n2. Open `index.html` in your browser\n\nGenerated by Kopiiki\n"
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


def rewrite_html_dom(html_content, url_mapping, page_url):
    soup = BeautifulSoup(html_content, "html.parser")
    tags_to_attrs = {
        'img': 'src', 'link': 'href', 'script': 'src',
        'source': 'src', 'video': 'src', 'audio': 'src'
    }
    from urllib.parse import urljoin
    for tag_name, attr in tags_to_attrs.items():
        for tag in soup.find_all(tag_name):
            original = tag.get(attr)
            if original:
                abs_url = urljoin(page_url, original)
                if abs_url in url_mapping:
                    tag[attr] = "./" + url_mapping[abs_url] if './' not in url_mapping[abs_url] else url_mapping[abs_url]
                elif original in url_mapping:
                    tag[attr] = "./" + url_mapping[original] if './' not in url_mapping[original] else url_mapping[original]
    
    for a in soup.find_all('a'):
        href = a.get('href')
        if href:
            abs_url = urljoin(page_url, href)
            normalized = abs_url.rstrip('/')
            match_found = False
            for key, val in url_mapping.items():
                if key.rstrip('/') == normalized and val.endswith('.html'):
                    a['href'] = val
                    match_found = True
                    break
            if not match_found and abs_url in url_mapping and url_mapping[abs_url].endswith('.html'):
                 a['href'] = url_mapping[abs_url]
                 
    # Strip integrity and crossorigin attributes to prevent strict browser loading failures
    # when local assets have been modified or served from a different origin.
    for tag in soup.find_all(['link', 'script', 'img', 'video', 'audio', 'source']):
        if 'integrity' in tag.attrs:
            del tag['integrity']
        if 'crossorigin' in tag.attrs:
            del tag['crossorigin']
                 
    return str(soup)

def rewrite_css_urls(css_content, url_mapping):
    if not isinstance(css_content, str):
        try:
            css_content = css_content.decode('utf-8')
        except:
            return css_content
    def replace_url(match):
        original_url = match.group(1).strip("'\"")
        mapped_url = url_mapping.get(original_url, original_url)
        if mapped_url != original_url:
             mapped_url = "../" + mapped_url.replace("./", "")
        return f"url('{mapped_url}')"
    import re
    return re.sub(r'url\((.*?)\)', replace_url, css_content)

def create_zip_file(html_results, captured_assets, start_url, output_dir, extract_id):
    import tempfile, uuid, os, json, re, zipfile, requests
    from bs4 import BeautifulSoup
    from urllib.parse import urlparse, urljoin, unquote
    from datetime import datetime
    
    if isinstance(html_results, str):
        html_results = {start_url: html_results}
        
    temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
    
    page_files = {}
    url_mapping = {}
    
    for page_url, html in html_results.items():
        if page_url == start_url or page_url.rstrip('/') == start_url.rstrip('/'):
            page_files[page_url] = "index.html"
            url_mapping[page_url] = "./index.html"
            url_mapping[page_url.rstrip('/')] = "./index.html"
        else:
            path = urlparse(page_url).path.strip('/')
            name = path.replace('/', '_') if path else "index"
            if not name.endswith('.html'): name += '.html'
            page_files[page_url] = name
            url_mapping[page_url] = "./" + name
            url_mapping[page_url.rstrip('/')] = "./" + name

    session_obj = requests.Session()
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.0.0 Safari/537.36'}

    global_assets = {'css': set(), 'js': set(), 'img': set(), 'fonts': set(), 'favicons': set(), 'videos': set(), 'audio': set()}
    components_dump = {}
    
    for page_url, html in html_results.items():
        # Pass session to extract_assets to maintain global persistence
        page_assets = extract_assets(html, page_url, session_obj=session_obj, headers=headers, captured_assets=captured_assets)
        for k in global_assets.keys():
            if k in page_assets:
                global_assets[k].update(page_assets[k])
                
        if page_url == start_url:
            components_dump = page_assets.get('components', {})

    downloaded_buffers = {}
    filename_counter = {}

    for asset_type, urls in global_assets.items():
        for asset_url in urls:
            formatted_url = urljoin(start_url, asset_url)
            if not formatted_url.startswith(('http://', 'https://')): continue
                
            parsed_asset = urlparse(formatted_url)
            filename = os.path.basename(unquote(parsed_asset.path))
            if not filename: filename = f"{uuid.uuid4().hex[:8]}"
            name, ext = os.path.splitext(filename)
            
            if not ext:
                ext_map = {'css': '.css', 'js': '.js', 'img': '.png', 'fonts': '.woff2', 'favicons': '.ico', 'videos': '.mp4', 'audio': '.mp3'}
                ext = ext_map.get(asset_type, '')
            
            name = re.sub(r'[^a-zA-Z0-9._\-]', '_', name)
            filename = f"{name[:50]}{ext}"
            
            if filename in filename_counter:
                filename_counter[filename] += 1
                filename = f"{name[:50]}_{filename_counter[filename]}{ext}"
            else:
                filename_counter[filename] = 0
                
            file_path = f"{asset_type}/{filename}"
            url_mapping[asset_url] = file_path   
            if formatted_url != asset_url:
                url_mapping[formatted_url] = file_path
            
            if formatted_url in captured_assets and captured_assets[formatted_url]:
                downloaded_buffers[file_path] = captured_assets[formatted_url]
            elif asset_url in captured_assets and captured_assets[asset_url]:
                downloaded_buffers[file_path] = captured_assets[asset_url]
            else:
                try:
                    response = session_obj.get(formatted_url, timeout=10, headers=headers, verify=False)
                    if response.status_code == 200: downloaded_buffers[file_path] = response.content
                except Exception:
                    pass

    with zipfile.ZipFile(temp_zip.name, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for page_url, html in html_results.items():
            final_html = rewrite_html_dom(html, url_mapping, page_url)
            zipf.writestr(page_files[page_url], final_html)
            
        for file_path, content in downloaded_buffers.items():
            if file_path.startswith("css/"):
                content = rewrite_css_urls(content, url_mapping)
            zipf.writestr(file_path, content)
            
        for asset_type in ['css', 'js', 'img', 'fonts', 'favicons', 'videos', 'audio']:
            zipf.writestr(f'{asset_type}/.gitkeep', '')
            
        if components_dump:
            zipf.writestr('components/.gitkeep', '')
            for (component_type, components) in components_dump.items():
                if components:
                    zipf.writestr(f'components/{component_type}/.gitkeep', '')
                    for (i, component) in enumerate(components):
                        html_code = component.get('html', '')
                        if html_code:
                            zipf.writestr(f'components/{component_type}/component_{i + 1}.html', html_code)
                            
        parsed_domain = urlparse(start_url).netloc
        readme = f"# Kopiiki Website Clone: {parsed_domain}\n\n"
        readme += f"Generated by Kopiiki Multi-Page Crawler on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        readme += f"## 📄 Extracted Pages ({len(html_results)})\n"
        for p_url, p_file in page_files.items():
            readme += f"- `{p_file}` (Source: {p_url})\n"
        
        readme += f"\n## 📦 Downloaded Assets ({len(downloaded_buffers)})\n"
        for asset_type, urls in global_assets.items():
            if urls:
                readme += f"- **{asset_type.upper()}**: {len(urls)} files\n"
                
        readme += f"\n## 🚀 Next Steps for LLM\n"
        readme += f"All absolute URLs have been rewritten to local paths binding these assets logically to the DOM. "
        readme += f"You may now use these HTML files as ground-truth layout references for React component generation.\n"
        
        zipf.writestr('README.md', readme)
        
    return temp_zip.name

