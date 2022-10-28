#!/bin/sh

npm run build_staging
mv dist dist-staging

npm run build
mv dist dist-prod