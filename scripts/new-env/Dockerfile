# Fork dependencies on Python 3.12 (requirements-py312.txt). The fork itself is installed at run time from /src.
FROM python:3.12-slim
COPY requirements-py312.txt /opt/new-env/
RUN pip install -q --root-user-action=ignore --disable-pip-version-check -r /opt/new-env/requirements-py312.txt \
 && pip freeze > /opt/new-env/freeze.txt
