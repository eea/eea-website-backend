FROM eeacms/plone-backend:6.1.3-11
ENV PROFILES="eea.website.policy:default"

COPY requirements.txt constraints.txt /app/
RUN ./bin/pip install -r requirements.txt -c constraints.txt \
    && find /app -not -user plone -exec chown plone:plone {} \+
