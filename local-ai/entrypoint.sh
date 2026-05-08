#!/bin/sh
set -e

# Boot the Ollama API server in the background ...
echo "[local-ai] starting ollama serve..."
ollama serve &
SERVER_PID=$!

# ... wait for it to accept commands ...
echo "[local-ai] waiting for server..."
while true; do
    if ollama list >/dev/null 2>&1; then
        break
    fi
    sleep 1
done
echo "[local-ai] server up."

# ... ensure the configured model is pulled. Re-running is a no-op once cached.
if [ -n "$LOCAL_AI_MODEL" ]; then
    if ollama list | awk 'NR>1 {print $1}' | grep -qx "$LOCAL_AI_MODEL"; then
        echo "[local-ai] model already cached: $LOCAL_AI_MODEL"
    else
        echo "[local-ai] pulling $LOCAL_AI_MODEL — this can take a while on first start"
        if ! ollama pull "$LOCAL_AI_MODEL"; then
            echo "[local-ai] pull failed; the OpenAI endpoint will return errors until it succeeds"
        else
            echo "[local-ai] pull complete."
        fi
    fi
else
    echo "[local-ai] LOCAL_AI_MODEL is empty — skipping pull. Pull manually with: ollama pull <tag>"
fi

# Hand control to the server process.
wait "$SERVER_PID"
