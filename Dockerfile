FROM eeacms/plone-backend:6.0.13-14
ENV PROFILES="eea.website.policy:default"

COPY requirements.txt constraints.txt /app/
RUN ./bin/pip install -r requirements.txt -c constraints.txt \
 && ./bin/pip install -f https://eggrepo.eea.europa.eu/simple/ plone.volto==4.4.5.dev1 \
 && find /app -not -user plone -exec chown plone:plone {} \+
