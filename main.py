#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scraper de Contactos Idealista
Extrae teléfonos y emails de viviendas de particulares en Idealista España
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import urllib.request
import urllib.parse
from bs4 import BeautifulSoup
from datetime import datetime
import logging
import re
import os
import time

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Diccionario de ciudades disponibles para scraping
CIUDADES_ESPANA = {
    'madrid': 'https://www.idealista.com/venta-viviendas/madrid-madrid/con-particulares/',
    'barcelona': 'https://www.idealista.com/venta-viviendas/barcelona-barcelona/con-particulares/',
    'valladolid': 'https://www.idealista.com/venta-viviendas/valladolid-valladolid/con-particulares/',
    'valencia': 'https://www.idealista.com/venta-viviendas/valencia-valencia/con-particulares/',
    'sevilla': 'https://www.idealista.com/venta-viviendas/sevilla-sevilla/con-particulares/',
    'zaragoza': 'https://www.idealista.com/venta-viviendas/zaragoza-zaragoza/con-particulares/',
    'malaga': 'https://www.idealista.com/venta-viviendas/malaga-malaga/con-particulares/',
    'murcia': 'https://www.idealista.com/venta-viviendas/murcia-murcia/con-particulares/',
    'bilbao': 'https://www.idealista.com/venta-viviendas/bilbao/con-particulares/',
    'alicante': 'https://www.idealista.com/venta-viviendas/alicante-alicante/con-particulares/',
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'es-ES,es;q=0.9',
    'Connection': 'keep-alive',
}

def extract_phone_from_text(text):
    """Extrae números de teléfono del texto"""
    if not text:
        return []
    
    # Patrones comunes de teléfonos españoles
    patterns = [
        r'(\+34|0034)?\s*[6789]\d{2}\s*\d{2}\s*\d{2}\s*\d{2}',  # Móvil
        r'(\+34|0034)?\s*9\d{2}\s*\d{2}\s*\d{2}\s*\d{2}',  # Fijo
        r'[6789]\d{8}',  # 9 dígitos sin espacios
    ]
    
    phones = []
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        phones.extend(matches)
    
    # Limpiar y normalizar
    cleaned_phones = []
    for phone in phones:
        if isinstance(phone, tuple):
            phone = ''.join(phone)
        # Eliminar espacios y caracteres especiales
        phone = re.sub(r'[\s\-\.]', '', phone)
        # Añadir +34 si no lo tiene
        if not phone.startswith('+'):
            if phone.startswith('0034'):
                phone = '+34' + phone[4:]
            elif phone.startswith('34'):
                phone = '+' + phone
            else:
                phone = '+34' + phone
        if phone not in cleaned_phones and len(phone) >= 11:
            cleaned_phones.append(phone)
    
    return cleaned_phones

def extract_email_from_text(text):
    """Extrae emails del texto"""
    if not text:
        return []
    
    pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    emails = re.findall(pattern, text, re.IGNORECASE)
    return list(set(emails))

def scrape_property_detail(property_url):
    """Scrape la página de detalle de una propiedad para extraer contactos"""
    try:
        req = urllib.request.Request(property_url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=25) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        
        soup = BeautifulSoup(html, "html.parser")
        
        contacts = {
            'phones': [],
            'emails': []
        }
        
        # Buscar en todo el texto de la página
        page_text = soup.get_text()
        contacts['phones'] = extract_phone_from_text(page_text)
        contacts['emails'] = extract_email_from_text(page_text)
        
        # Buscar en elementos específicos
        contact_elements = soup.select('.contact-info, .phone, .email, [class*="contact"], [class*="phone"], [class*="email"]')
        for elem in contact_elements:
            elem_text = elem.get_text()
            contacts['phones'].extend(extract_phone_from_text(elem_text))
            contacts['emails'].extend(extract_email_from_text(elem_text))
        
        # Eliminar duplicados
        contacts['phones'] = list(set(contacts['phones']))
        contacts['emails'] = list(set(contacts['emails']))
        
        return contacts
        
    except Exception as e:
        logger.error(f"Error scraping detail {property_url}: {e}")
        return {'phones': [], 'emails': []}

def build_search_url(base_url: str, page: int = 1) -> str:
    """Construye URL de búsqueda para una ciudad y página"""
    if page <= 1:
        return base_url
    return f"{base_url}pagina-{page}.htm"

def scrape_idealista_contacts(base_url: str, page: int = 1, max_properties: int = 10):
    """Extrae contactos de propiedades de particulares en Idealista"""
    search_url = build_search_url(base_url, page)
    req = urllib.request.Request(search_url, headers=HEADERS)
    
    with urllib.request.urlopen(req, timeout=25) as resp:
        html = resp.read().decode("utf-8", errors="ignore")
    
    soup = BeautifulSoup(html, "html.parser")
    properties = []
    
    for article in soup.find_all("article", class_="item"):
        if len(properties) >= max_properties:
            break
            
        # Verificar que es de particular
        seller_type = "Particular"
        extra_info = article.select_one(".item-extra-info, .item-subtitle")
        if extra_info:
            extra_text = extra_info.get_text(strip=True)
            if re.search(r"agencia|inmobiliaria", extra_text, re.I):
                continue  # Saltar agencias
        
        title_el = article.select_one("a.item-link")
        price_el = article.select_one(".item-price span, span.item-price")
        location_el = article.select_one(".item-location")
        
        url_rel = title_el["href"] if title_el and title_el.has_attr("href") else None
        if url_rel and not url_rel.startswith("http"):
            url_abs = urllib.parse.urljoin("https://www.idealista.com", url_rel)
        else:
            url_abs = url_rel
        
        if not url_abs:
            continue
        
        # Extraer ID
        id_match = re.search(r"/inmueble/(\d+)/", url_abs or "")
        prop_id = id_match.group(1) if id_match else None
        
        # Scrape contactos de la página de detalle
        logger.info(f"Scraping contacts for property {prop_id}...")
        contacts = scrape_property_detail(url_abs)
        
        # Solo añadir si tiene contactos
        if contacts['phones'] or contacts['emails']:
            properties.append({
                "id": prop_id,
                "titulo": title_el.get_text(strip=True) if title_el else "",
                "precio": price_el.get_text(strip=True) if price_el else "",
                "ubicacion": location_el.get_text(" ", strip=True) if location_el else "",
                "url": url_abs,
                "telefonos": contacts['phones'],
                "emails": contacts['emails'],
                "fecha_scraping": datetime.now().isoformat()
            })
        
        # Pausa para evitar rate limiting
        time.sleep(2)
    
    logger.info(f"Encontradas {len(properties)} propiedades con contactos")
    return properties

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'service': 'Idealista Contacts Scraper API'
    }), 200

@app.route('/api/contacts/<city>', methods=['GET'])
def get_contacts(city='madrid'):
    try:
        city = city.lower()
        base_url = CIUDADES_ESPANA.get(city, CIUDADES_ESPANA['madrid'])
        city_name = city.capitalize()
        
        page = int(request.args.get('page', 1))
        max_properties = int(request.args.get('limit', 10))
        
        logger.info(f"Scraping contacts from {city_name}, page {page}")
        data = scrape_idealista_contacts(base_url, page=page, max_properties=max_properties)
        
        return jsonify({
            'success': True,
            'timestamp': datetime.now().isoformat(),
            'location': city_name,
            'page': page,
            'count': len(data),
            'data': data
        }), 200
        
    except Exception as e:
        logger.error(f"Error en endpoint: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/api/cities', methods=['GET'])
def get_cities():
    return jsonify({
        'success': True,
        'cities': list(CIUDADES_ESPANA.keys())
    }), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
