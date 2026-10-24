FROM nginx:1.27-alpine
COPY frontend/public /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
# On a server the app talks to its own API by default; `?source=mock` still opens the offline demo.
# (The source file keeps "mock" so the same index.html runs offline, from a file or as a published demo.)
RUN sed -i 's/get("source") || "mock"/get("source") || "server"/' /usr/share/nginx/html/index.html \
 && grep -q 'get("source") || "server"' /usr/share/nginx/html/index.html
