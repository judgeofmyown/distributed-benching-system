FROM golang:1.22-alpine
RUN apk add --no-cache gcc musl-dev
WORKDIR /app
RUN mkdir -p /app/submission
EXPOSE 8888
CMD ["sh", "-c", "go build -o /app/engine /app/submission/exchange_server.go && /app/engine"]
