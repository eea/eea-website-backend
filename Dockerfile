FROM plone/plone-backend:6.1.3 as base
ENV PROFILES="eea.website.policy:default"

# Custom plone.volto version fixes for:
# https://taskman.eionet.europa.eu/issues/284346#note-8
COPY requirements.txt constraints.txt /app/
COPY ./etc/zodbpack.conf /app/etc/zodbpack.conf
RUN ./bin/pip install -r requirements.txt -c constraints.txt \
    && find /app -not -user plone -exec chown plone:plone {} \+
