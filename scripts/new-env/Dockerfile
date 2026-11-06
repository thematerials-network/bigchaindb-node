# Fork dependencies on Python 3.12 (requirements-py312.txt). The fork itself is installed at run time from /src.
FROM python:3.12-slim
COPY requirements-py312.txt requirements-py312-test.txt install-requirements.sh /opt/new-env/
RUN /opt/new-env/install-requirements.sh pip /opt/new-env/requirements-py312.txt -q --root-user-action=ignore --disable-pip-version-check \
 && pip install -q --root-user-action=ignore --disable-pip-version-check --require-hashes --no-deps -r /opt/new-env/requirements-py312-test.txt \
 && pip freeze > /opt/new-env/freeze.txt
