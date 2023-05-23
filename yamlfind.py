#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Find a key or value in yaml files. Usefull for searching hiera data yaml files in puppet

Usage:
  yamlfind.py [-d] [-s] [-k] <find> <filenames> [<filenames>] [<filenames>] [<filenames>] [<filenames>] [<filenames>] [<filenames>] 
  yamlfind.py [-d] (-h | --help)
  yamlfind.py [-d] --version
  yamlfind.py [-d] 

Options:
  -h --help     Show this screen.
  --version     Show version.
  --search -s   Search for value
  --key -k      Search for key
  --debug -d    Debug arguments

"""
from docopt import docopt  # builds argument options from the documentation above
import yaml
import glob

"""Example with output
yamlfind.py -s -k classes '*.yaml' 'common/*' 'os/*.yaml' 'os/*/*.yaml'

common.yaml:
  classes: ['profile::base', 'packages::manage', 'stdlib::manage']
common/zabbix_agent2.yaml:
  classes: ['stdlib::manage', 'zabbix_agent2']
common/puppet_agent.yaml:
  classes: ['puppet_agent']
os/RedHat.yaml:
  classes: ['profile::redhat', 'access_insights_client']
"""

if __name__ == '__main__':
  arguments = docopt(__doc__, version='Yaml find 1.0')
  if arguments.get('--debug'):
    print(arguments)

  find = arguments.get('<find>')
  for filename in arguments.get('<filenames>'):
    files = glob.glob(filename) # expand globs, will be a list of files
    for file in files:
      foundinfile = False
      with open(file, 'r') as stream:
        try:
          content = yaml.safe_load(stream)
          if content:
            for k,v in content.items():
              if not isinstance(v,bool):
                if (arguments.get('--key') and find in str(k)) or (arguments.get('--search') and find in str(v)):
                  if not foundinfile:
                    print(f"{file}: ")
                    foundinfile = True
                    print(f"  {k}: {v}")
        except yaml.YAMLError as exc:
          print(exc)
