#!/usr/bin/env bash
# Read-only host inventory. No env, credentials, application rows or container logs.
set -u
export LC_ALL=C
if [ -e /.dockerenv ] || [ -e /run/.containerenv ]; then
  printf '%s\n' 'ERROR: estás dentro de un contenedor. Ejecuta desde la consola del VPS en Contabo o una sesión SSH al servidor; no desde Bash de un servicio Easypanel.' >&2
  exit 2
fi
section() { printf '\n%s\n' "### $1"; }
run() {
  if command -v timeout >/dev/null 2>&1; then timeout 25s "$@"; else "$@"; fi
  local result=$?
  if [ "$result" -ne 0 ]; then printf 'No disponible: %s (código %s)\n' "$1" "$result" >&2; fi
  return 0
}
section 'Fecha UTC'
date -u '+%Y-%m-%dT%H:%M:%SZ'
section 'CPU y memoria del host'
run nproc
run free -m
section 'Espacio e inodos (sin recorrer archivos)'
run df -h / /var/lib/docker
run df -i / /var/lib/docker
if ! command -v docker >/dev/null 2>&1; then
  printf '%s\n' 'Docker CLI no disponible. Diagnóstico incompleto.' >&2; exit 3
fi
section 'Docker y modo de orquestación'
run docker version --format '{{json .Server.Version}}'
run docker info --format 'Swarm={{.Swarm.LocalNodeState}} Manager={{.Swarm.ControlAvailable}} CPUs={{.NCPU}} MemoryBytes={{.MemTotal}} DockerRoot={{.DockerRootDir}}'
run docker compose version
section 'Servicios: solo nombre, imagen y réplicas'
run docker service ls --format '{{.Name}} | {{.Image}} | {{.Replicas}}'
section 'Contenedores: nombre, imagen, estado y puertos'
run docker ps --format '{{.Names}} | {{.Image}} | {{.Status}} | {{.Ports}}'
section 'Uso instantáneo (no es un pico de carga)'
run docker stats --no-stream --format '{{.Name}} | CPU={{.CPUPerc}} | RAM={{.MemUsage}} | RAMpct={{.MemPerc}}'
section 'Redes'
run docker network ls --format '{{.ID}} | {{.Name}} | {{.Driver}} | {{.Scope}}'
section 'Volúmenes: únicamente nombres'
run docker volume ls --format '{{.Name}}'
section 'Servicios propios de semaforos: límites, montajes y redes'
# Whitelist fields explicitly; never emit docker inspect in full.
while IFS= read -r service_id; do
  [ -n "$service_id" ] || continue
  run docker service inspect "$service_id" --format 'Name={{.Spec.Name}} Resources={{json .Spec.TaskTemplate.Resources}} Mounts={{json .Spec.TaskTemplate.ContainerSpec.Mounts}} Networks={{json .Spec.TaskTemplate.Networks}}'
done < <(run docker service ls --filter name=semaforos --format '{{.ID}}')
section 'Fin'
printf '%s\n' 'Inventario sin cambios. No se han instalado, reiniciado ni eliminado servicios. No certifica respaldo ni capacidad disponible bajo carga.'
