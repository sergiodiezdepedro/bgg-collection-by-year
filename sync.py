#!/usr/bin/env python3
import os
import sys
import time
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
import json
import html
import re

# Configuration
URL_FILE_PATH = "peticion_BGG_xml_juegos_base_by_year.txt"
LOCAL_XML_PATH = "collection.xml"
OUTPUT_HTML_PATH = "index.html"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 BGGCollectionSync/1.0"

def get_bgg_url():
    """Reads the API URL from the request file."""
    if not os.path.exists(URL_FILE_PATH):
        print(f"Error: No se encontró el archivo '{URL_FILE_PATH}'.")
        print("Creando archivo con URL por defecto para 'pezhammer'...")
        default_url = "https://boardgamegeek.com/xmlapi2/collection?username=pezhammer&subtype=boardgame&excludesubtype=boardgameexpansion&stats=1&own=1"
        with open(URL_FILE_PATH, "w", encoding="utf-8") as f:
            f.write(default_url)
        return default_url

    with open(URL_FILE_PATH, "r", encoding="utf-8") as f:
        url = f.read().strip()
        if not url:
            print("Error: El archivo de petición está vacío. Usando URL por defecto.")
            return "https://boardgamegeek.com/xmlapi2/collection?username=pezhammer&subtype=boardgame&excludesubtype=boardgameexpansion&stats=1&own=1"
        return url

def fetch_bgg_xml(url):
    """Fetches the XML from BGG, handling HTTP 202 queue status and retrying."""
    req = urllib.request.Request(url)
    req.add_header("User-Agent", USER_AGENT)
    
    max_retries = 12
    retry_delay = 5  # seconds
    
    for attempt in range(1, max_retries + 1):
        print(f"Llamando a la API de BoardGameGeek (Intento {attempt}/{max_retries})...")
        try:
            with urllib.request.urlopen(req) as response:
                status_code = response.status
                xml_content = response.read()
                
                # Check for HTTP 202 (Accepted - Queued)
                if status_code == 202:
                    print(f"BGG está procesando tu colección (Cola). Reintentando en {retry_delay} segundos...")
                    time.sleep(retry_delay)
                    continue
                
                # Parse XML to see if it's a queued message
                try:
                    root = ET.fromstring(xml_content)
                    if root.tag == "message":
                        message_text = root.text or ""
                        if "accepted" in message_text.lower() or "process" in message_text.lower() or "queued" in message_text.lower():
                            print(f"Respuesta de BGG: '{message_text}'. Reintentando en {retry_delay} segundos...")
                            time.sleep(retry_delay)
                            continue
                        else:
                            print(f"Error BGG message: {message_text}")
                            sys.exit(1)
                    
                    if root.tag == "errors":
                        error_elem = root.find("error/message")
                        error_text = error_elem.text if error_elem is not None else "Error desconocido de BGG"
                        print(f"Error devuelto por BGG: {error_text}")
                        sys.exit(1)
                        
                    # Successful fetch
                    print(f"¡Sincronización completada! Descargados {len(xml_content)} bytes.")
                    return xml_content
                    
                except ET.ParseError as pe:
                    print(f"Error al analizar el XML recibido: {pe}")
                    print("Contenido recibido:")
                    print(xml_content[:500])
                    sys.exit(1)
                    
        except urllib.error.HTTPError as e:
            if e.code == 202:
                print(f"BGG devolvió HTTP 202 (Procesando). Reintentando en {retry_delay} segundos...")
                time.sleep(retry_delay)
                continue
            else:
                raise e
        except urllib.error.URLError as e:
            raise e
            
    raise Exception("Se superó el número máximo de reintentos para la API de BGG.")

def parse_games(xml_content):
    """Parses games list from the BGG XML content."""
    # Handle case where file content includes HTML/text before XML
    # (happens when downloading XML from browser)
    if isinstance(xml_content, bytes):
        xml_content = xml_content.decode('utf-8', errors='ignore')
    
    if isinstance(xml_content, str):
        # Find where actual XML starts
        xml_start = xml_content.find('<items')
        if xml_start == -1:
            xml_start = xml_content.find('<?xml')
        if xml_start > 0:
            xml_content = xml_content[xml_start:]
        
        # Clean XML: remove invalid characters that might cause parsing errors
        # Remove control characters except tab, newline, carriage return
        xml_content = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]', '', xml_content)
        
        # Convert back to bytes for ET.fromstring
        xml_content = xml_content.encode('utf-8')
    
    # Try parsing with defusedxml if available, otherwise use standard ET
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        # Try with error recovery - remove problematic sequences
        xml_str = xml_content.decode('utf-8', errors='ignore')
        # Escape any unescaped ampersands that aren't part of XML entities
        xml_str = re.sub(r'&(?![a-zA-Z#][a-zA-Z0-9]*;)', '&amp;', xml_str)
        xml_content = xml_str.encode('utf-8')
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e2:
            print(f"Error al parsear XML: {e2}")
            print(f"Detalles: {e2.args}")
            raise
    
    games = []
    
    items = root.findall("item")
    print(f"Procesando {len(items)} elementos encontrados en el XML...")
    
    for item in items:
        subtype = item.get("subtype")
        if subtype != "boardgame":
            continue
            
        objectid = item.get("objectid")
        
        # Name (always inside <name>)
        name_elem = item.find("name")
        name = name_elem.text if name_elem is not None else "Juego Desconocido"
        
        # Year
        year_elem = item.find("yearpublished")
        year = 0
        if year_elem is not None and year_elem.text:
            try:
                year = int(year_elem.text)
            except ValueError:
                pass
                
        # Image and Thumbnail (clean protocol relative URLs)
        thumbnail_elem = item.find("thumbnail")
        thumbnail = thumbnail_elem.text if thumbnail_elem is not None else ""
        if thumbnail and thumbnail.startswith("//"):
            thumbnail = "https:" + thumbnail
            
        image_elem = item.find("image")
        image = image_elem.text if image_elem is not None else ""
        if image and image.startswith("//"):
            image = "https:" + image
            
        # Stats
        stats_elem = item.find("stats")
        minplayers = 1
        maxplayers = 99
        playingtime = 0
        rating = 0.0
        
        if stats_elem is not None:
            minplayers_attr = stats_elem.get("minplayers")
            if minplayers_attr:
                try:
                    minplayers = int(minplayers_attr)
                except ValueError:
                    pass
                    
            maxplayers_attr = stats_elem.get("maxplayers")
            if maxplayers_attr:
                try:
                    maxplayers = int(maxplayers_attr)
                except ValueError:
                    pass
                    
            playingtime_attr = stats_elem.get("playingtime")
            if playingtime_attr:
                try:
                    playingtime = int(playingtime_attr)
                except ValueError:
                    pass
                    
            rating_elem = stats_elem.find("rating")
            if rating_elem is not None:
                average_elem = rating_elem.find("average")
                if average_elem is not None:
                    average_val = average_elem.get("value")
                    try:
                        rating = round(float(average_val), 1) if average_val else 0.0
                    except ValueError:
                        pass
                        
        games.append({
            "id": objectid,
            "name": name,
            "year": year,
            "thumbnail": thumbnail if thumbnail else "https://placehold.co/150x150/1e293b/cbd5e1?text=No+Art",
            "image": image if image else "https://placehold.co/300x300/1e293b/cbd5e1?text=No+Art",
            "minplayers": minplayers,
            "maxplayers": maxplayers,
            "playingtime": playingtime,
            "rating": rating
        })
        
    # Sort games by Year (ascending), then Name
    games.sort(key=lambda g: (g["year"], g["name"].lower()))
    return games

def get_html_template(games_json_str, username):
    """Returns the visual index.html template injected with the parsed JSON string."""
    return f"""<!doctype html>
<html lang="es">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>BGG Dashboard - {html.escape(username)}</title>
    
    <!-- Favicon -->
    <link rel="icon" type="image/x-icon" href="https://boardgamegeek.com/favicon.ico">
    
    <!-- Google Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    
    <style>
      :root {{
        /* Dark Theme (Default) */
        --bg-color: #080c14;
        --card-bg: #121826;
        --card-border: #1e293b;
        --card-hover-border: #7c3aed;
        --accent-purple: #7c3aed;
        --accent-teal: #0d9488;
        --text-primary: #f8fafc;
        --text-secondary: #94a3b8;
        --glass-bg: rgba(18, 24, 38, 0.7);
        --glass-border: rgba(255, 255, 255, 0.05);
        --input-bg: rgba(255, 255, 255, 0.03);
        --input-border: rgba(255, 255, 255, 0.08);
      }}

      body.light-theme {{
        /* Light Theme */
        --bg-color: #f8fafc;
        --card-bg: #ffffff;
        --card-border: #e2e8f0;
        --card-hover-border: #7c3aed;
        --accent-purple: #7c3aed;
        --accent-teal: #0d9488;
        --text-primary: #1e293b;
        --text-secondary: #64748b;
        --glass-bg: rgba(248, 250, 252, 0.7);
        --glass-border: rgba(0, 0, 0, 0.08);
        --input-bg: rgba(0, 0, 0, 0.03);
        --input-border: rgba(0, 0, 0, 0.08);
      }}

      * {{
        box-sizing: border-box;
        margin: 0;
        padding: 0;
      }}

      body {{
        background-color: var(--bg-color);
        background-image: 
          radial-gradient(at 0% 0%, rgba(13, 148, 136, 0.12) 0px, transparent 40%),
          radial-gradient(at 100% 100%, rgba(124, 58, 237, 0.12) 0px, transparent 40%);
        color: var(--text-primary);
        font-family: 'Outfit', system-ui, -apple-system, sans-serif;
        min-height: 100vh;
        padding-bottom: 50px;
        line-height: 1.5;
        overflow-x: hidden;
        transition: background-color 0.3s ease, color 0.3s ease;
      }}

      body.light-theme {{
        background-image: 
          radial-gradient(at 0% 0%, rgba(13, 148, 136, 0.08) 0px, transparent 40%),
          radial-gradient(at 100% 100%, rgba(124, 58, 237, 0.08) 0px, transparent 40%);
      }}

      /* Custom scrollbar */
      ::-webkit-scrollbar {{
        width: 8px;
      }}
      ::-webkit-scrollbar-track {{
        background: var(--bg-color);
      }}
      ::-webkit-scrollbar-thumb {{
        background: var(--card-border);
        border-radius: 4px;
      }}
      ::-webkit-scrollbar-thumb:hover {{
        background: var(--accent-purple);
      }}

      header {{
        position: relative;
        padding: 60px 20px 40px;
        text-align: center;
        background: linear-gradient(180deg, rgba(18, 24, 38, 0.8) 0%, transparent 100%);
        border-bottom: 1px solid var(--glass-border);
      }}

      body.light-theme header {{
        background: linear-gradient(180deg, rgba(248, 250, 252, 0.8) 0%, transparent 100%);
      }}

      header h1 {{
        font-size: 2.8rem;
        font-weight: 800;
        letter-spacing: -0.05em;
        margin-bottom: 8px;
        background: linear-gradient(to right, #0dd3c5, #a78bfa);
        -webkit-background-clip: text;
        background-clip: text;
        -webkit-text-fill-color: transparent;
      }}

      header h1 strong {{
        font-weight: 800;
      }}

      header p {{
        font-size: 1.1rem;
        color: var(--text-secondary);
        font-weight: 300;
      }}

      .container {{
        width: 95%;
        max-width: 1300px;
        margin: auto;
        padding: 24px 10px;
      }}

      /* Stats Dashboard */
      .stats-panel {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        gap: 20px;
        margin-bottom: 40px;
      }}

      .stat-card {{
        background: var(--glass-bg);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid var(--glass-border);
        border-radius: 16px;
        padding: 20px;
        display: flex;
        align-items: center;
        gap: 16px;
        transition: transform 0.3s ease, border-color 0.3s ease;
      }}

      .stat-card:hover {{
        transform: translateY(-4px);
        border-color: rgba(124, 58, 237, 0.3);
      }}

      .stat-icon {{
        font-size: 2rem;
        padding: 12px;
        border-radius: 12px;
        background: rgba(255, 255, 255, 0.03);
        display: flex;
        align-items: center;
        justify-content: center;
      }}

      .stat-card:nth-child(1) .stat-icon {{ color: #0d9488; }}
      .stat-card:nth-child(2) .stat-icon {{ color: #7c3aed; }}
      .stat-card:nth-child(3) .stat-icon {{ color: #3b82f6; }}
      .stat-card:nth-child(4) .stat-icon {{ color: #eab308; }}

      .stat-info .stat-val {{
        font-size: 1.8rem;
        font-weight: 700;
        line-height: 1.2;
      }}

      .stat-info .stat-label {{
        font-size: 0.85rem;
        color: var(--text-secondary);
        text-transform: uppercase;
        letter-spacing: 0.05em;
        font-weight: 500;
      }}

      /* Controls Panel */
      .controls-bar {{
        background: var(--glass-bg);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid var(--glass-border);
        border-radius: 20px;
        padding: 24px;
        margin-bottom: 30px;
        display: flex;
        flex-direction: column;
        gap: 20px;
      }}

      .controls-row-main {{
        display: grid;
        grid-template-columns: 2fr 1fr 1fr 1fr;
        gap: 16px;
      }}

      @media (max-width: 900px) {{
        .controls-row-main {{
          grid-template-columns: 1fr 1fr;
        }}
      }}

      @media (max-width: 600px) {{
        .controls-row-main {{
          grid-template-columns: 1fr;
        }}
      }}

      .input-wrapper {{
        position: relative;
        display: flex;
        align-items: center;
      }}

      .input-icon {{
        position: absolute;
        left: 14px;
        color: var(--text-secondary);
        font-size: 1.1rem;
      }}

      .search-input {{
        width: 100%;
        padding: 12px 12px 12px 42px;
        background: var(--input-bg);
        border: 1px solid var(--input-border);
        border-radius: 12px;
        color: var(--text-primary);
        font-family: inherit;
        font-size: 0.95rem;
        transition: border-color 0.3s ease, box-shadow 0.3s ease;
      }}

      .search-input:focus {{
        outline: none;
        border-color: var(--accent-purple);
        box-shadow: 0 0 0 3px rgba(124, 58, 237, 0.15);
      }}

      .select-input {{
        padding: 12px;
        background: var(--input-bg);
        border: 1px solid var(--input-border);
        border-radius: 12px;
        color: var(--text-primary);
        font-family: inherit;
        font-size: 0.95rem;
        cursor: pointer;
        width: 100%;
        transition: border-color 0.3s, box-shadow 0.3s;
      }}

      .select-input:focus {{
        outline: none;
        border-color: var(--accent-teal);
        box-shadow: 0 0 0 3px rgba(13, 148, 136, 0.15);
      }}

      .select-input option {{
        background: var(--card-bg);
        color: var(--text-primary);
      }}

      .tag-filters {{
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        align-items: center;
      }}

      .tag-label {{
        font-size: 0.85rem;
        color: var(--text-secondary);
        font-weight: 500;
        margin-right: 6px;
      }}

      .filter-tag {{
        padding: 6px 14px;
        background: var(--input-bg);
        border: 1px solid var(--input-border);
        border-radius: 20px;
        color: var(--text-secondary);
        font-size: 0.85rem;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.2s ease;
      }}

      .filter-tag:hover {{
        background: rgba(255, 255, 255, 0.08);
        color: var(--text-primary);
      }}

      body.light-theme .filter-tag:hover {{
        background: rgba(0, 0, 0, 0.08);
      }}

      .filter-tag.active {{
        background: linear-gradient(135deg, var(--accent-purple), #9061f9);
        border-color: var(--accent-purple);
        color: white;
        box-shadow: 0 4px 12px rgba(124, 58, 237, 0.25);
      }}

      .view-toggle-btn {{
        background: var(--input-bg);
        border: 1px solid var(--input-border);
        color: var(--text-secondary);
        padding: 12px 18px;
        border-radius: 12px;
        cursor: pointer;
        display: flex;
        align-items: center;
        gap: 8px;
        font-family: inherit;
        font-size: 0.95rem;
        font-weight: 500;
        transition: all 0.3s;
      }}

      .view-toggle-btn:hover {{
        border-color: var(--text-secondary);
        color: var(--text-primary);
      }}

      /* Theme Toggle Button */
      .theme-toggle-btn {{
        position: absolute;
        top: 20px;
        right: 20px;
        background: var(--input-bg);
        border: 1px solid var(--input-border);
        color: var(--text-secondary);
        padding: 10px 14px;
        border-radius: 12px;
        cursor: pointer;
        display: flex;
        align-items: center;
        gap: 8px;
        font-family: inherit;
        font-size: 0.95rem;
        font-weight: 500;
        transition: all 0.3s;
      }}

      .theme-toggle-btn:hover {{
        border-color: var(--text-secondary);
        color: var(--text-primary);
      }}

      /* Games Count Summary */
      .count-summary {{
        margin-bottom: 24px;
        font-size: 0.95rem;
        color: var(--text-secondary);
        display: flex;
        justify-content: space-between;
        align-items: center;
      }}

      .count-summary span strong {{
        color: var(--text-primary);
      }}

      /* Games Grid Layout */
      .games-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
        gap: 28px;
        transition: all 0.3s;
      }}

      .game-card {{
        background: var(--card-bg);
        border: 1px solid var(--card-border);
        border-radius: 20px;
        overflow: hidden;
        display: flex;
        flex-direction: column;
        position: relative;
        transition: transform 0.35s cubic-bezier(0.16, 1, 0.3, 1), border-color 0.3s, box-shadow 0.35s;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
        text-decoration: none;
        color: inherit;
      }}

      .game-card:hover {{
        transform: translateY(-8px);
        border-color: var(--card-hover-border);
        box-shadow: 0 12px 30px rgba(124, 58, 237, 0.15);
      }}

      /* Game Image */
      .game-img-container {{
        aspect-ratio: 1;
        width: 100%;
        background: #0d111a;
        display: flex;
        align-items: center;
        justify-content: center;
        position: relative;
        overflow: hidden;
        border-bottom: 1px solid var(--glass-border);
      }}

      body.light-theme .game-img-container {{
        background: #f0f4f8;
      }}

      .game-img {{
        width: 90%;
        height: 90%;
        object-fit: contain;
        transition: transform 0.5s ease;
      }}

      .game-card:hover .game-img {{
        transform: scale(1.06);
      }}

      /* Overlay Badges */
      .year-badge {{
        position: absolute;
        top: 14px;
        left: 14px;
        background: rgba(15, 23, 42, 0.8);
        backdrop-filter: blur(8px);
        border: 1px solid rgba(255, 255, 255, 0.1);
        padding: 4px 10px;
        border-radius: 30px;
        font-size: 0.8rem;
        font-weight: 600;
        color: #cbd5e1;
      }}

      .rating-badge {{
        position: absolute;
        top: 14px;
        right: 14px;
        padding: 4px 10px;
        border-radius: 30px;
        font-size: 0.8rem;
        font-weight: 700;
        display: flex;
        align-items: center;
        gap: 4px;
        backdrop-filter: blur(8px);
      }}

      /* Rating Color Grading */
      .rating-high {{
        background: rgba(16, 185, 129, 0.15);
        color: #34d399;
        border: 1px solid rgba(16, 185, 129, 0.3);
      }}
      .rating-medium {{
        background: rgba(45, 212, 191, 0.15);
        color: #2dd4bf;
        border: 1px solid rgba(45, 212, 191, 0.3);
      }}
      .rating-low {{
        background: rgba(245, 158, 11, 0.15);
        color: #fbbf24;
        border: 1px solid rgba(245, 158, 11, 0.3);
      }}
      .rating-poor {{
        background: rgba(239, 68, 68, 0.15);
        color: #f87171;
        border: 1px solid rgba(239, 68, 68, 0.3);
      }}

      /* Card Content */
      .game-details {{
        padding: 20px;
        display: flex;
        flex-direction: column;
        flex-grow: 1;
      }}

      .game-title {{
        font-size: 1.1rem;
        font-weight: 600;
        color: var(--text-primary);
        margin-bottom: 12px;
        line-height: 1.3;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
        height: 2.6rem;
      }}

      .game-specs {{
        display: flex;
        flex-direction: column;
        gap: 8px;
        margin-top: auto;
        border-top: 1px solid rgba(255, 255, 255, 0.05);
        padding-top: 12px;
      }}

      .spec-item {{
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 0.85rem;
        color: var(--text-secondary);
      }}

      .spec-icon {{
        font-size: 1rem;
        width: 16px;
        text-align: center;
      }}

      /* List View styling */
      .games-list-view {{
        display: flex;
        flex-direction: column;
        gap: 12px;
      }}

      .games-list-view .game-card {{
        flex-direction: row;
        height: 100px;
        align-items: center;
        padding: 10px 24px;
      }}

      .games-list-view .game-img-container {{
        width: 80px;
        height: 80px;
        aspect-ratio: auto;
        border-radius: 12px;
        border: none;
      }}

      .games-list-view .game-details {{
        flex-direction: row;
        align-items: center;
        justify-content: space-between;
        padding: 0 0 0 20px;
        flex-grow: 1;
        width: 100%;
      }}

      .games-list-view .game-title {{
        margin-bottom: 0;
        height: auto;
        max-width: 40%;
        display: -webkit-box;
        -webkit-box-orient: vertical;
        -webkit-line-clamp: 1;
        line-clamp: 1;
        overflow: hidden;
        font-size: 1.15rem;
      }}

      .games-list-view .year-badge {{
        position: static;
        margin-right: 12px;
      }}

      .games-list-view .rating-badge {{
        position: static;
      }}

      .games-list-view .game-specs {{
        flex-direction: row;
        gap: 24px;
        margin-top: 0;
        border-top: none;
        padding-top: 0;
        align-items: center;
      }}

      @media (max-width: 800px) {{
        .games-list-view .game-card {{
          flex-direction: column;
          height: auto;
          align-items: stretch;
          padding: 20px;
        }}
        .games-list-view .game-img-container {{
          width: 100%;
          height: 180px;
        }}
        .games-list-view .game-details {{
          flex-direction: column;
          align-items: stretch;
          padding: 16px 0 0 0;
        }}
        .games-list-view .game-title {{
          max-width: 100%;
          margin-bottom: 12px;
        }}
        .games-list-view .game-specs {{
          flex-direction: column;
          align-items: flex-start;
          gap: 8px;
          border-top: 1px solid rgba(255, 255, 255, 0.05);
          padding-top: 12px;
        }}
      }}

      /* Empty State */
      .empty-state {{
        grid-column: 1 / -1;
        text-align: center;
        padding: 80px 20px;
        background: var(--glass-bg);
        border: 1px solid var(--glass-border);
        border-radius: 20px;
        color: var(--text-secondary);
      }}

      .empty-state h3 {{
        color: var(--text-primary);
        font-size: 1.4rem;
        margin-bottom: 10px;
      }}

      /* Footer */
      footer {{
        text-align: center;
        padding: 40px 20px;
        color: var(--text-secondary);
        font-size: 0.9rem;
        font-weight: 300;
        border-top: 1px solid var(--glass-border);
        margin-top: 60px;
        background: linear-gradient(0deg, rgba(18, 24, 38, 0.4) 0%, transparent 100%);
      }}
      
      footer strong {{
        color: var(--accent-teal);
        font-weight: 500;
      }}

      footer a {{
        color: var(--accent-teal);
      }}

      /* Scroll to Top Button */
      #scroll-to-top {{
        position: fixed;
        bottom: 30px;
        right: 30px;
        width: 50px;
        height: 50px;
        background: linear-gradient(135deg, var(--accent-purple), #9061f9);
        border: none;
        border-radius: 50%;
        cursor: pointer;
        display: none;
        align-items: center;
        justify-content: center;
        font-size: 1.5rem;
        box-shadow: 0 4px 16px rgba(124, 58, 237, 0.4);
        transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
        z-index: 1000;
        backdrop-filter: blur(8px);
        border: 1px solid rgba(255, 255, 255, 0.1);
      }}

      #scroll-to-top:hover {{
        transform: translateY(-4px);
        box-shadow: 0 8px 24px rgba(124, 58, 237, 0.6);
        background: linear-gradient(135deg, #9061f9, var(--accent-purple));
      }}

      #scroll-to-top:active {{
        transform: translateY(-2px);
      }}

      #scroll-to-top.show {{
        display: flex;
      }}

      @media (max-width: 768px) {{
        #scroll-to-top {{
          bottom: 20px;
          right: 20px;
          width: 45px;
          height: 45px;
          font-size: 1.3rem;
        }}
      }}
    </style>
  </head>

  <body>
    <header>
      <button id="theme-toggle" class="theme-toggle-btn" aria-label="Cambiar tema">🌙 Oscuro</button>
      <h1>Colección BGG de <strong>{html.escape(username)}</strong></h1>
      <p>Juegos de mesa base organizados de forma interactiva</p>
    </header>

    <div class="container">
      <!-- Stats Panel -->
      <section class="stats-panel">
        <div class="stat-card">
          <div class="stat-icon">🎲</div>
          <div class="stat-info">
            <div class="stat-val" id="stat-total-games">-</div>
            <div class="stat-label">Total Juegos</div>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon">⏳</div>
          <div class="stat-info">
            <div class="stat-val" id="stat-timeline">-</div>
            <div class="stat-label">Años de Rango</div>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon">⭐</div>
          <div class="stat-info">
            <div class="stat-val" id="stat-avg-rating">-</div>
            <div class="stat-label">Nota Media BGG</div>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon">👥</div>
          <div class="stat-info">
            <div class="stat-val" id="stat-solo-friendly">-</div>
            <div class="stat-label">Juegos Solitario</div>
          </div>
        </div>
      </section>

      <!-- Controls Panel -->
      <section class="controls-bar">
        <div class="controls-row-main">
          <!-- Search input -->
          <div class="input-wrapper">
            <span class="input-icon">🔍</span>
            <input type="text" id="search-input" class="search-input" placeholder="Buscar juego por nombre..." />
          </div>

          <!-- Sort dropdown -->
          <select id="sort-select" class="select-input">
            <option value="year-asc">Año: Más antiguos primero</option>
            <option value="year-desc">Año: Más recientes primero</option>
            <option value="name-asc">Nombre: A - Z</option>
            <option value="name-desc">Nombre: Z - A</option>
            <option value="rating-desc">Nota BGG: Más alta primero</option>
          </select>

          <!-- Players Filter -->
          <select id="players-select" class="select-input">
            <option value="all">Cualquier Nº Jugadores</option>
            <option value="1">Solo 1 Jugador (Solitario)</option>
            <option value="2">2 Jugadores</option>
            <option value="3">3 Jugadores</option>
            <option value="4">4+ Jugadores</option>
          </select>

          <!-- View Toggle -->
          <button id="view-toggle" class="view-toggle-btn">
            <span id="view-toggle-icon">▤</span>
            <span id="view-toggle-text">Vista Lista</span>
          </button>
        </div>

        <!-- Tag Quick Filters -->
        <div class="tag-filters">
          <span class="tag-label">Filtros Rápidos:</span>
          <button class="filter-tag active" data-filter="all">Todos</button>
          <button class="filter-tag" data-filter="solo">Solitarios</button>
          <button class="filter-tag" data-filter="highly-rated">Top Valorados (≥ 7.8)</button>
          <button class="filter-tag" data-filter="classic">Clásicos (< 2010)</button>
          <button class="filter-tag" data-filter="modern">Modernos (≥ 2020)</button>
          <button class="filter-tag" data-filter="short">Partidas Cortas (≤ 45 min)</button>
          <button class="filter-tag" data-filter="long">Partidas Largas (≥ 90 min)</button>
        </div>
      </section>

      <!-- Count Header -->
      <div class="count-summary">
        <span id="showing-summary">Mostrando <strong>-</strong> de <strong>-</strong> juegos</span>
      </div>

      <!-- Games List Grid -->
      <section id="games-container" class="games-grid">
        <!-- Rendered dynamically via JS -->
      </section>
    </div>

    <footer>
      Generado automáticamente a partir del XML de BoardGameGeek. Diseñado por <strong><a href="https://pezhammer.wordpress.com/">pezhammer</a> + IA</strong>.
    </footer>

    <!-- Scroll to Top Button -->
    <button id="scroll-to-top" aria-label="Volver arriba">↑</button>

    <!-- Injected Game Data -->
    <script>
      const gamesData = {games_json_str};
      
      // State Management
      let currentView = 'grid'; // 'grid' or 'list'
      let activeQuickFilter = 'all';
      
      // DOM Elements
      const searchInput = document.getElementById('search-input');
      const sortSelect = document.getElementById('sort-select');
      const playersSelect = document.getElementById('players-select');
      const viewToggleBtn = document.getElementById('view-toggle');
      const viewToggleIcon = document.getElementById('view-toggle-icon');
      const viewToggleText = document.getElementById('view-toggle-text');
      const gamesContainer = document.getElementById('games-container');
      const showingSummary = document.getElementById('showing-summary');
      const tagButtons = document.querySelectorAll('.filter-tag');

      // Stats Elements
      const statTotalGames = document.getElementById('stat-total-games');
      const statTimeline = document.getElementById('stat-timeline');
      const statAvgRating = document.getElementById('stat-avg-rating');
      const statSoloFriendly = document.getElementById('stat-solo-friendly');

      // Theme Toggle
      const themeToggleBtn = document.getElementById('theme-toggle');

      // Theme Management Functions
      function loadTheme() {{
        const savedTheme = localStorage.getItem('bgg-theme') || 'dark';
        applyTheme(savedTheme);
      }}

      function applyTheme(theme) {{
        if (theme === 'light') {{
          document.body.classList.add('light-theme');
          themeToggleBtn.textContent = '☀️ Claro';
          localStorage.setItem('bgg-theme', 'light');
        }} else {{
          document.body.classList.remove('light-theme');
          themeToggleBtn.textContent = '🌙 Oscuro';
          localStorage.setItem('bgg-theme', 'dark');
        }}
      }}

      function toggleTheme() {{
        const currentTheme = localStorage.getItem('bgg-theme') || 'dark';
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        applyTheme(newTheme);
      }}

      // Initial Setup
      function init() {{
        // Load saved theme preference
        loadTheme();
        
        // Set up global stats once based on whole collection
        calculateGlobalStats();
        
        // Initial render
        renderGames();
        
        // Listeners
        searchInput.addEventListener('input', renderGames);
        sortSelect.addEventListener('change', renderGames);
        playersSelect.addEventListener('change', renderGames);
        
        // Theme toggle
        themeToggleBtn.addEventListener('click', toggleTheme);
        
        // View Toggle Listener
        viewToggleBtn.addEventListener('click', () => {{
          if (currentView === 'grid') {{
            currentView = 'list';
            gamesContainer.className = 'games-list-view';
            viewToggleIcon.textContent = '㗊';
            viewToggleText.textContent = 'Vista Cuadrícula';
          }} else {{
            currentView = 'grid';
            gamesContainer.className = 'games-grid';
            viewToggleIcon.textContent = '▤';
            viewToggleText.textContent = 'Vista Lista';
          }}
          renderGames();
        }});

        // Quick Tag filters
        tagButtons.forEach(btn => {{
          btn.addEventListener('click', () => {{
            tagButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            activeQuickFilter = btn.getAttribute('data-filter');
            renderGames();
          }});
        }});
      }}

      // Calculate global stats of entire collection
      function calculateGlobalStats() {{
        if (gamesData.length === 0) return;
        
        statTotalGames.textContent = gamesData.length;
        
        // Timeline calculation
        const years = gamesData.map(g => g.year).filter(y => y > 0);
        if (years.length > 0) {{
          const minYear = Math.min(...years);
          const maxYear = Math.max(...years);
          statTimeline.textContent = `${{minYear}} - ${{maxYear}}`;
        }} else {{
          statTimeline.textContent = 'N/A';
        }}
        
        // Average BGG rating
        const ratings = gamesData.map(g => g.rating).filter(r => r > 0);
        if (ratings.length > 0) {{
          const avg = ratings.reduce((sum, val) => sum + val, 0) / ratings.length;
          statAvgRating.textContent = avg.toFixed(1);
        }} else {{
          statAvgRating.textContent = 'N/A';
        }}
        
        // Solo playable
        const soloGames = gamesData.filter(g => g.minplayers <= 1).length;
        statSoloFriendly.textContent = soloGames;
      }}

      // Filter, Sort and Render Games
      function renderGames() {{
        let filtered = [...gamesData];
        
        // 1. Search Query filter
        const query = searchInput.value.toLowerCase().trim();
        if (query) {{
          filtered = filtered.filter(g => g.name.toLowerCase().includes(query));
        }}
        
        // 2. Players Filter
        const playerCount = playersSelect.value;
        if (playerCount !== 'all') {{
          const count = parseInt(playerCount);
          if (count === 4) {{
            filtered = filtered.filter(g => g.maxplayers >= 4);
          }} else {{
            filtered = filtered.filter(g => g.minplayers <= count && g.maxplayers >= count);
          }}
        }}

        // 3. Quick Tag Filters
        if (activeQuickFilter !== 'all') {{
          if (activeQuickFilter === 'solo') {{
            filtered = filtered.filter(g => g.minplayers <= 1);
          }} else if (activeQuickFilter === 'highly-rated') {{
            filtered = filtered.filter(g => g.rating >= 7.8);
          }} else if (activeQuickFilter === 'classic') {{
            filtered = filtered.filter(g => g.year > 0 && g.year < 2010);
          }} else if (activeQuickFilter === 'modern') {{
            filtered = filtered.filter(g => g.year >= 2020);
          }} else if (activeQuickFilter === 'short') {{
            filtered = filtered.filter(g => g.playingtime > 0 && g.playingtime <= 45);
          }} else if (activeQuickFilter === 'long') {{
            filtered = filtered.filter(g => g.playingtime >= 90);
          }}
        }}

        // 4. Sorting
        const sortBy = sortSelect.value;
        if (sortBy === 'year-asc') {{
          filtered.sort((a, b) => a.year - b.year || a.name.localeCompare(b.name));
        }} else if (sortBy === 'year-desc') {{
          filtered.sort((a, b) => b.year - a.year || a.name.localeCompare(b.name));
        }} else if (sortBy === 'name-asc') {{
          filtered.sort((a, b) => a.name.localeCompare(b.name));
        }} else if (sortBy === 'name-desc') {{
          filtered.sort((a, b) => b.name.localeCompare(a.name));
        }} else if (sortBy === 'rating-desc') {{
          filtered.sort((a, b) => b.rating - a.rating || a.name.localeCompare(b.name));
        }}

        // 5. Render HTML
        showingSummary.innerHTML = `Mostrando <strong>${{filtered.length}}</strong> de <strong>${{gamesData.length}}</strong> juegos`;
        
        if (filtered.length === 0) {{
          gamesContainer.innerHTML = `
            <div class="empty-state">
              <h3>No se encontraron juegos</h3>
              <p>Prueba a cambiar tus filtros o la búsqueda.</p>
            </div>
          `;
          return;
        }}

        gamesContainer.innerHTML = filtered.map(game => {{
          // Rating class
          let ratingClass = 'rating-poor';
          if (game.rating >= 8.0) ratingClass = 'rating-high';
          else if (game.rating >= 7.0) ratingClass = 'rating-medium';
          else if (game.rating >= 6.0) ratingClass = 'rating-low';

          // Format players spec
          let playersSpec = '';
          if (game.minplayers === game.maxplayers) {{
            playersSpec = `${{game.minplayers}} jugador${{game.minplayers > 1 ? 'es' : ''}}`;
          }} else {{
            playersSpec = `${{game.minplayers}}-${{game.maxplayers}} jugadores`;
          }}
          if (game.minplayers <= 1) {{
            playersSpec = `👥 Solo (${{playersSpec}})`;
          }} else {{
            playersSpec = `👥 ${{playersSpec}}`;
          }}

          // Image src
          const thumbnail = game.thumbnail || 'https://placehold.co/150x150/1e293b/cbd5e1?text=No+Art';

          return `
            <a href="https://boardgamegeek.com/boardgame/${{game.id}}"class="game-card" title="Ver en BoardGameGeek">
              <div class="game-img-container">
                <img class="game-img" src="${{thumbnail}}" alt="${{htmlEscape(game.name)}}" loading="lazy" />
                <span class="year-badge">${{game.year > 0 ? game.year : 'N/A'}}</span>
                <span class="rating-badge ${{ratingClass}}">⭐ ${{game.rating.toFixed(1)}}</span>
              </div>
              <div class="game-details">
                <h3 class="game-title" title="${{htmlEscape(game.name)}}">${{htmlEscape(game.name)}}</h3>
                <div class="game-specs">
                  <div class="spec-item">
                    <span class="spec-icon">${{game.minplayers <= 1 ? '👤' : '👥'}}</span>
                    <span>${{playersSpec}}</span>
                  </div>
                  <div class="spec-item">
                    <span class="spec-icon">⏱️</span>
                    <span>${{game.playingtime > 0 ? game.playingtime + ' minutos' : 'Tiempo desconocido'}}</span>
                  </div>
                </div>
              </div>
            </a>
          `;
        }}).join('');
      }}

      // Quick helper to escape HTML inside dynamic string interpolation
      function htmlEscape(str) {{
        return str
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;')
          .replace(/"/g, '&quot;')
          .replace(/'/g, '&#39;');
      }}

      // Scroll to Top Button Logic
      const scrollToTopBtn = document.getElementById('scroll-to-top');
      
      // Show/hide button based on scroll position
      window.addEventListener('scroll', () => {{
        if (window.pageYOffset > 300) {{
          scrollToTopBtn.classList.add('show');
        }} else {{
          scrollToTopBtn.classList.remove('show');
        }}
      }});
      
      // Smooth scroll to top on button click
      scrollToTopBtn.addEventListener('click', () => {{
        window.scrollTo({{
          top: 0,
          behavior: 'smooth'
        }});
      }});

      // Launch on DOM Content Load
      document.addEventListener('DOMContentLoaded', init);
    </script>
  </body>
</html>
"""

def main():
    print("=== Sincronizador de Colección BGG ===")
    
    # 1. Get request URL
    bgg_url = get_bgg_url()
    print(f"URL de BGG: {bgg_url}")
    
    # Extract username from URL for custom titles
    username = "pezhammer"
    if "username=" in bgg_url:
        try:
            username = bgg_url.split("username=")[1].split("&")[0]
        except IndexError:
            pass
            
    # 2. Fetch or load data
    xml_content = None
    if os.path.exists(LOCAL_XML_PATH):
        print(f"Detectado archivo XML local '{LOCAL_XML_PATH}'. Cargando datos de colección locales...")
        try:
            with open(LOCAL_XML_PATH, "rb") as f:
                xml_content = f.read()
                # Remove BOM if present (UTF-8 with BOM)
                if xml_content.startswith(b'\xef\xbb\xbf'):
                    xml_content = xml_content[3:]
        except Exception as e:
            print(f"Error al leer '{LOCAL_XML_PATH}': {e}")
            sys.exit(1)
    else:
        print(f"No se detectó '{LOCAL_XML_PATH}'. Intentando descargar colección desde BGG...")
        try:
            xml_content = fetch_bgg_xml(bgg_url)
        except Exception as e:
            print(f"\n[!] Error al descargar colección: {e}")
            print(f"\n[⚠️] AVISO IMPORTANTE SOBRE BGG API Y CLOUDFLARE:")
            print("Las llamadas directas desde servidores o entornos automatizados a menudo son bloqueadas")
            print("por BoardGameGeek o Cloudflare devolviendo un código 401 Unauthorized (requiriendo tokens Bearer).")
            print("\nPara solucionar esto fácilmente y generar tu dashboard interactivo:")
            print(f"1. Copia y abre esta URL en el navegador de tu máquina local:")
            print(f"   {bgg_url}")
            print(f"2. Tu navegador descargará el archivo XML de tu colección. Guarda el contenido")
            print(f"   con el nombre de archivo '{LOCAL_XML_PATH}' en esta misma carpeta:")
            print(f"   /Users/pezhammer/Desarrollo/A-E/bgg-collection-by-year/")
            print("3. Ejecuta de nuevo este script ('python3 sync.py'). Detectará el archivo")
            print("   local automáticamente, omitirá la descarga bloqueada y creará tu web premium offline.")
            sys.exit(1)
            
    # 3. Parse data
    games = parse_games(xml_content)
    print(f"¡Procesamiento completado exitosamente! Se cargaron {len(games)} juegos.")
    
    # 4. Generate JSON string
    games_json_str = json.dumps(games, ensure_ascii=False, indent=2)
    
    # 5. Write generated HTML
    html_content = get_html_template(games_json_str, username)
    
    with open(OUTPUT_HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html_content)
        
    print(f"¡Dashboard interactivo guardado con éxito en '{OUTPUT_HTML_PATH}'!")
    print(f"Puedes abrir '{OUTPUT_HTML_PATH}' en tu navegador para ver la colección.")
    print("=======================================")

if __name__ == "__main__":
    main()
