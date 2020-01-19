# Getting started

# Containers

## proxy

This container has nginx, does HTTPS using a Let's Encrypt cert, and forwards traffic to `web`.

## web

This is the web app, written in aiohttp for the backend and Vue.js for the frontend.

## jobs

This runs in the background processing jobs. `fetch` jobs download a copy of everyone's tweets; `delete` jobs delete old tweets based on rules.

## db

This runs postgres. Data about is stored here, as well as databases of everyone's tweets. Both `backend` and `jobs` store their data here.
