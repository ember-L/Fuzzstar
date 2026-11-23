#!/bin/sh
set -eu

# Compose 会把 backend/.env 注入所有服务；本机使用的 127.0.0.1 在容器内不可达，
# 因此用同一份 MYSQL_* 配置生成容器内的 DATABASE_URL。
if [ -n "${MYSQL_DATABASE:-}" ] && [ -n "${MYSQL_USER:-}" ] && [ -n "${MYSQL_PASSWORD:-}" ]; then
    export DATABASE_URL="mysql+pymysql://${MYSQL_USER}:${MYSQL_PASSWORD}@mysql:3306/${MYSQL_DATABASE}?charset=utf8mb4"
fi

exec "$@"
