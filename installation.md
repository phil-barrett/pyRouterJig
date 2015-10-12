---
layout: default
title: pyRouterJig Installation
---

Prerequisites
=============

At this stage of the project, pyRouterJig is likely not easily installed for someone
completely unfamiliar with getting [Python](http://www.python.org)
applications running on their partiuclarly platform.  All I have access
to is a Mac running OSX 10.9.2, so I won\'t be much help debugging other
installations.

pyRouterJig depends upon the following [Python](http://www.python.org)
packages, which must be installed in order to run pyRouterJig:

* [Python](http://www.python.org).  Python is installed by default on
  the Mac, but I use a slighly different version, as I will discuss below.
* [Matplotlib](http://www.matplotlib.org}).  This package is used for
  drawing the joints and Incra template.  My long-term plan is to remove the
  dependency on this package.
* [PyQt4](http://pyqt.sourceforge.net).  This package is used as the
  graphical user interface (GUI).

I install all of these packages using [Anaconda](https://www.continuum.io/),
which is also available for Windows, Mac, and Linux.  I highly recommend Anaconda,
as the packages above may have other dependencies that Anaconda also takes
care of installing.

Installation
============

After unzipping (or untarring) the download file, locate the file
<b>pyRouterJig</b>.  Assuming that you satisfy the Prequisites above and have
those files in your path, on Mac and Linux you should be able to type in a terminal

./pyRouterJig

and the application should start.  On Windows, I don\'t know how to run python
scripts, and this documentation will be updated once I receive that feedback.


