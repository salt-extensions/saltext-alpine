``saltext-alpine``: Salt Extension for Alpine Linux
====================================================

This extension adds first-class Alpine Linux support to Salt by providing
execution modules for the two subsystems Salt core does not cover on Alpine:

- **pkg** (``saltext.alpine.modules.apk``) -- package management via ``apk``
- **service** (``saltext.alpine.modules.openrc``) -- service management via OpenRC

Both modules register under Salt's standard virtual names, so existing states
such as ``pkg.installed`` and ``service.running`` work on Alpine minions
without any changes to your state files.

.. toctree::
  :maxdepth: 2
  :caption: Guides
  :hidden:

  topics/installation

.. toctree::
  :maxdepth: 2
  :caption: Provided Modules
  :hidden:

  ref/modules/index

.. toctree::
  :maxdepth: 2
  :caption: Reference
  :hidden:

  changelog


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
