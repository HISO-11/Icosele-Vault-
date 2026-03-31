# Icosele VM Terraform Provider

Manage Icosele VM VMs and snapshots as Terraform resources.

## Status

This is a provider skeleton — source files only, not a compiled binary.
Full provider coming post-launch.

## How It Will Work

The provider communicates with Icosele VM's REST API (port 47820)
to create, read, update, and delete VM resources declaratively.

## Building (future)

```bash
go build -o terraform-provider-icosele_vm
```

See HashiCorp's [provider development guide](https://developer.hashicorp.com/terraform/plugin/framework).

## Usage

See `main.tf.example` for a complete configuration example.

## Contribute

github.com/HISO-11/icosele-vm
