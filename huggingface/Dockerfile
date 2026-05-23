FROM ghcr.io/cqshushu/iptv-spider:latest

COPY scripts/update_onetv_m3u.py /app/scripts/update_onetv_m3u.py
COPY scripts/start-with-onetv-updater.sh /app/scripts/start-with-onetv-updater.sh

RUN rm -rf /app/data && ln -s /data /app/data

RUN chmod +x /app/scripts/start-with-onetv-updater.sh /app/scripts/update_onetv_m3u.py

ENTRYPOINT ["/app/scripts/start-with-onetv-updater.sh"]
CMD ["python", "wsgi.py"]
