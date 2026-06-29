# CyM Liquidaciones API

API para liquidación automática de sueldos TV Crecer S.R.L.

## Deploy en Railway

1. Subir esta carpeta a un repo de GitHub
2. Entrar a railway.app → New Project → Deploy from GitHub
3. Seleccionar el repo
4. Railway detecta automáticamente el Procfile y despliega

## Endpoint principal

POST /liquidar
- Body: multipart/form-data
- Campo: file (el Excel .xls con las novedades del mes)
- Respuesta: JSON con netós + PDF y TXT en base64

## Uso desde n8n

1. Nodo Gmail Trigger → detecta mail con adjunto
2. Nodo HTTP Request → POST a https://tu-api.railway.app/liquidar con el adjunto
3. Nodo Code → decodifica PDF y TXT de base64
4. Nodo Google Drive → sube los archivos
5. Nodo Gmail → notifica al contador
