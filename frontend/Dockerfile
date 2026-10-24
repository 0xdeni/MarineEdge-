FROM nginx:1.27-alpine
# The app is static files talking to its own server's /api. The detailed map (if an admin downloads it)
# lives on the shared data volume and is served from /tiles/ with range requests (see nginx.conf).
COPY frontend/public /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
# The service worker's cache name carries a hash of the app files, so phones pick up every new version
# (and only then): a changed sw.js makes the browser install the new worker, which swaps the cached shell.
RUN cd /usr/share/nginx/html \
 && H=$(find . -type f ! -name sw.js -exec md5sum {} + | sort -k 2 | md5sum | cut -c1-10) \
 && sed -i "s/^const VERSION = 'marineedge-[^']*';/const VERSION = 'marineedge-$H';/" sw.js \
 && grep -q "marineedge-$H" sw.js
