from setuptools import setup, find_packages

setup(
  name="pypns",
  version="0.2.0",
  description="Push Notification Gateway for Apple (APNS) and Google (C2DM) services.",
  author="ggarber",
  author_email="gustavogb@gmail.com",
  license="MIT",
  url="http://github.com/ggarber/pypns",
  download_url="http://github.com/ggarber/pypns",
  classifiers = [
    'Development Status :: 4 - Beta',
    'Environment :: Web Environment',
    'Intended Audience :: Developers',
    'License :: OSI Approved :: MIT License',
    'Operating System :: OS Independent',
    'Programming Language :: Python',
    'Topic :: Software Development :: Libraries :: Python Modules'],
  packages=find_packages(),
  package_data={},
  install_requires=['Twisted>=8.2.0', 'pyOpenSSL>=0.10']
)
