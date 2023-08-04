# HOW TO BUILD WITH FLIT
Info see: https://realpython.com/pypi-publish-python-package/#prepare-your-package-for-publication

Three steps:
(save pyproject.toml if any)
- flit init (this directory)
update pyproject.toml to include dependencies (see other .toml files as example)
- flit build
this creates a dist directory, extract "dist/\*tar.gz" to see if all is in it (and the versions are right)
remove the extracted file
- flit publish
Get passwd of pypi.org and enter

Done
