FROM ollama/ollama:latest

COPY entrypoint.sh /entrypoint.sh
# Tolerant of Windows checkouts (strips CR before chmod).
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
