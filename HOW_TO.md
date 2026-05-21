# 📥 Instrucciones para crear el archivo HTML de la Colección BGG

## URL de Descarga

Abre esta URL en tu navegador web para descargar el archivo XML de tu colección:

```
https://boardgamegeek.com/xmlapi2/collection?username=pezhammer&subtype=boardgame&excludesubtype=boardgameexpansion&stats=1&own=1
```

**[Haz clic aquí para descargar](https://boardgamegeek.com/xmlapi2/collection?username=pezhammer&subtype=boardgame&excludesubtype=boardgameexpansion&stats=1&own=1)**

---

## Pasos de Descarga

1. **Abre la URL en tu navegador** (Chrome, Safari, Firefox, etc.)
2. El navegador **descargará automáticamente** un archivo llamado `collection.xml`
3. **Guarda el archivo** en la carpeta del proyecto:
   ```
   /Users/pezhammer/Desarrollo/A-E/bgg-collection-by-year/
   ```
4. **Ejecuta el script:**
   ```bash
   python3 sync.py
   ```
5. ✅ Se generará automáticamente el archivo `index.html` con tu dashboard interactivo

---

## Qué incluye esta descarga

✓ Todos tus juegos de mesa base (sin expansiones)  
✓ Datos de valoración BGG  
✓ Información de jugadores (mín/máx)  
✓ Tiempo de juego  
✓ Imágenes de portada  
✓ Año de publicación

---

## Parámetros de la URL

| Parámetro        | Valor                | Significa              |
| ---------------- | -------------------- | ---------------------- |
| `username`       | `pezhammer`          | Tu usuario en BGG      |
| `subtype`        | `boardgame`          | Solo juegos de mesa    |
| `excludesubtype` | `boardgameexpansion` | Excluir expansiones    |
| `stats`          | `1`                  | Incluir estadísticas   |
| `own`            | `1`                  | Solo juegos que posees |

Si necesitas modificar la consulta (ej: incluir expansiones, otro usuario), actualiza el archivo `peticion_BGG_xml_juegos_base_by_year.txt` con la nueva URL.

---

**Última actualización:** 21 de mayo de 2026
