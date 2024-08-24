FROM eeacms/plone-backend:6.0.11-12
ENV PROFILES="eea.website.policy:default"

COPY requirements.txt constraints.txt /app/
RUN ./bin/pip install -r requirements.txt -c constraints.txt \
 && find /app -not -user plone -exec chown plone:plone {} \+
