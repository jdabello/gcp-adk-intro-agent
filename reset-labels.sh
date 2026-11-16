#!/bin/bash

# Yesterday's date (YYYY-MM-DD). GNU date (Linux/Cloud Shell) uses -d,
# BSD date (macOS) uses -v.
YESTERDAY=$(date -d yesterday '+%Y-%m-%d' 2>/dev/null || date -v-1d '+%Y-%m-%d')

INSTANCES=`gcloud compute instances list \
    --project=$GOOGLE_CLOUD_PROJECT \
    --format='value(format("{0}:{1}", name,zone))'`
for INSTANCE in $INSTANCES; do
    NAME=${INSTANCE%%:*}
    ZONE=${INSTANCE#*:}
    gcloud compute instances remove-labels $NAME \
        --project=$GOOGLE_CLOUD_PROJECT \
        --zone=$ZONE \
        --labels=janitor-scheduled
    if [ $NAME == "gce-sbx-lnx-blob-01" ]; then
        gcloud compute instances add-labels $NAME \
            --project=$GOOGLE_CLOUD_PROJECT \
            --zone=$ZONE \
            --labels=janitor-scheduled=$YESTERDAY
    fi
done

gcloud compute instances list  \
    --project=$GOOGLE_CLOUD_PROJECT \
    --format='value(name, labels)'



