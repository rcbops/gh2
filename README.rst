===
gh2
===

An extensible (soon) tool take GitHub issues and convert it to any output
format.

.. warning::

    This is still a very young project.


Installation
============

At the moment, gh2 is not available on PyPI but it can be installed from
GitHub like so:

.. code-block:: shell

    pip install git+https://github.com/rcbops/gh2.git

Usage
=====

In order to avoid ratelimits, gh2 requires that you provide a Personal Access
Token from GitHub. Once you've done that you can export this in your
environment like so:

.. code-block:: shell

   export GITHUB_TOKEN=<personal access token from github>

With that variable defined in your environment, you can then do the following

.. code-block:: shell

   gh2csv --date-format '%Y-%m-%d' --output-file gh2results.csv rcbops/gh2

.. code-block:: shell

   gh2csv --date-format '%Y-%m-%dT%H:%M:%SZ' --output-file requests.csv kennethreitz/requests
