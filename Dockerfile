FROM eeacms/plone-backend:6.0.5-4
ENV PROFILES="eea.website.policy:default" \
    RELSTORAGE_BLOB_CACHE_SIZE=1000mb \
    ZEO_CLIENT_CACHE_SIZE=1000mb \
    ZODB_CACHE_SIZE=1000000

COPY requirements.txt constraints.txt /app/
RUN ./bin/pip install -r requirements.txt -c constraints.txt ${PIP_PARAMS} \
 && find /app -not -user plone -exec chown plone:plone {} \+
