#!/usr/bin/env python3
import argparse
import json
import math
import pprint
import re

import requests
import subprocess

CPU_REGEX = [
    r'Intel\(R\)[ ]Core\(TM\)[ ](\w\d)[-]\d+',
    r'Intel\(.*\)[ ]Xeon\(.*\)[ ]CPU[ ](E\d)[-]\d',
    r'.*(Pentium|Atom|Celeron).*',
]


class ComputerInfo:
    def __init__(self):
        self.name = ""
        self.asset_tag = ""
        self.memory = 0
        self.model_number = ""
        self.cpu_type = ""

    def __str__(self):
        s_out = """<ComputerInfo>:
 - Name:      {name}
 - Asset Tag: {asset_tag}
 - Memory:    {memory}
 - Model Num: {model_number}
 - CPU Type:  {cpu_type}
""".format(**self.__dict__)
        return s_out

    def get_all(self):
        self.get_asset_tag()
        self.get_cpu_type()
        self.get_hostname()
        self.get_memory_amount()
        self.get_model_number()

    def get_asset_tag(self):
        with open('/sys/devices/virtual/dmi/id/board_asset_tag', 'rb') as fd:
            output = fd.readline()
        self.asset_tag = output.decode().strip()

    def get_cpu_type(self):
        this_line = ""
        with open('/proc/cpuinfo', 'rb') as fd:
            for line in fd:
                this_line = line.decode().strip()
                if this_line.startswith('model name'):
                    break
        if this_line != "":
            for pattern in CPU_REGEX:
                result = re.search(pattern, this_line)
                if result:
                    self.cpu_type = result.group(1)
                    break

    def get_hostname(self):
        # Host name
        output = subprocess.check_output('/bin/hostname')
        self.name = output.decode().strip()

    def get_memory_amount(self):
        with open('/proc/meminfo', 'rb') as fd:
            for line in fd:
                if line.startswith(b'MemTotal'):
                    amt, unit = line.decode().split(':')[1].strip().split(' ')
                    break
        # Convert the memory value to gigabytes
        if unit == 'B':
            factor = 1024 * 1024 * 1024
        elif unit == 'kB':
            factor = 1024 * 1024
        else:
            factor = 1024
        try:
            self.memory = int(math.ceil(int(amt) / factor))
        except ValueError:
            self.memory = -1

    def get_model_number(self):
        with open('/sys/devices/virtual/dmi/id/product_name', 'rb') as fd:
            self.model_number = fd.readline().decode().strip()

    def set_asset_tag(self, assettag):
        self.asset_tag = assettag


class SnipeIt:
    def __init__(self, base_url, api_key):
        self.base_url = base_url
        self.headers = {
            'authorization': 'Bearer ' + api_key,
            'accept': 'application/json',
            'content-type': 'application/json'
        }

    def find_existing_asset(self, asset_tag):
        url = self.base_url + "/api/v1/hardware"
        querystring = {'search': asset_tag, 'sort': 'created_at', 'order': 'desc', 'limit': '1'}
        response = requests.request("GET", url, headers=self.headers, params=querystring)
        output = json.loads(response.text)
        if output['total'] > 0:
            return output['rows'][0]
        else:
            return None

    def find_model(self, model_number, cpu_type, memory_amount):
        url = self.base_url + "/api/v1/models"

        model_name = "{} {}/{}".format(model_number, cpu_type, memory_amount)

        querystring = {"limit": "1", "offset": "0", "search": model_name}

        response = requests.request('GET', url, headers=self.headers, params=querystring)
        output = json.loads(response.text)
        if output['total'] > 0:
            return output['rows'][0]
        else:
            return None

    def new_asset(self, computer_info, model_info):
        url = self.base_url + '/api/v1/hardware'

        payload = json.dumps({
            'asset_tag': computer_info.asset_tag,
            'status_id': 2,
            'model_id': model_info['id'],
            'name': computer_info.name
        })

        response = requests.request("POST", url, data=payload, headers=self.headers)
        return response.text


def main():
    parser = argparse.ArgumentParser(description="Create a new asset in Snipe-IT for the local computer")
    parser.add_argument('-n', '--dryrun', action='store_true')
    parser.add_argument('-a', '--assettag', default=None)

    args = parser.parse_args()

    # read the config.json
    with open('config.json') as fd:
        config = json.load(fd)

    snipeit_api = SnipeIt(config['baseUrl'], config['apiKey'])

    # collect the computer info
    my_computer = ComputerInfo()
    my_computer.get_all()
    if args.assettag is not None:
        my_computer.set_asset_tag(args.assettag)

    # check the database for the current asset tag
    result = snipeit_api.find_existing_asset(my_computer.asset_tag)
    if result and not args.dryrun:
        print('Asset already exits:', result)
    else:
        this_model = snipeit_api.find_model(my_computer.model_number, my_computer.cpu_type, my_computer.memory)
        if this_model:
            if not args.dryrun:
                if my_computer.asset_tag != "":
                    result = snipeit_api.new_asset(my_computer, this_model)
                    print(result)
                else:
                    print("[ERROR] Cannot add an asset with a blank tag")
                    print("[INFO] Try running: sudo cat /sys/devices/virtual/dmi/id/board_serial")
                    print("[INFO] Then run this script with -a ASSET_TAG")
            else:
                print("[DEBUG] Dry run, just displaying computer info...")
                print("[DEBUG] Model found:")
                pprint.pprint(this_model)
                print(str(my_computer))
        else:
            print("No model found for {} {}/{}".format(my_computer.model_number, my_computer.cpu_type, my_computer.memory))


if __name__ == '__main__':
    main()
