#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Find a key or value in yaml files. Usefull for searching hiera data yaml files in puppet

Usage:
  yamlfind.py [-d] [-r] [-s] [-k] <find> <filenames> [<filenames>] [<filenames>] [<filenames>] [<filenames>] [<filenames>] [<filenames>] 
  yamlfind.py [-d] [-r] [-s] [-k] <find>
  yamlfind.py [-d] [-r] (-h | --help)
  yamlfind.py [-d] --version
  yamlfind.py [-d] 

Options:
  -h --help       Show this screen.
  --version       Show version.
  --search -s     Search for value
  --key -k        Search for key
  --debug -d      Debug arguments
  --recursive -r  Recursive in subdirectories

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
  filenames = arguments.get('<filenames>')
  if len(filenames) == 0 and arguments.get('--recursive'):
      filenames = ['**/*.yaml',]
  if arguments.get('--debug'):
    print(arguments)
    print(f"{filenames=}")

  search_key = arguments.get('--key')
  search_search = arguments.get('--search')

  if not search_key and not search_search:
      search_search = True
      search_key = True
  i = 0
  find = arguments.get('<find>')
  for filename in filenames:
    files = glob.glob(filename, recursive=arguments.get('--recursive')) # expand globs, will be a list of files
    for file in files:
      foundinfile = False
      with open(file, 'r') as stream:
        try:
          content = yaml.safe_load(stream)
          i += 1
          if content:
            for k,v in content.items():
              if not isinstance(v,bool):
                if ( search_key and find in str(k)) or (search_search and find in str(v)):
                  if not foundinfile:
                    print(f"{file}: ")
                    foundinfile = True
                  print(f"  {k}: {v}")
              if isinstance(v,bool):
                if ( search_key and find in str(k)):
                  if not foundinfile:
                    print(f"{file}: ")
                    foundinfile = True
                  print(f"  {k}: {v}")

        except yaml.YAMLError as exc:
          print(exc)
