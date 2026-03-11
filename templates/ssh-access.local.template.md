# SSH Access Notes

## Bastion / Host
- Host: <hostname-or-ip>
- User: <username>
- Key path: <path-to-key>

## Useful commands
- `ssh <user>@<host>`
- `ssh -i <key> <user>@<host>`

## OpenClaw checks
- Base URL: <gateway-base-url>
- Origin header name: X-Nexo-Bridge-Key
- Token source: <where token is stored>
