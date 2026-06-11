FROM ubuntu:24.04 AS builder
RUN apt-get update && apt-get install -y g++ make

WORKDIR /build
COPY userCodeMain.cpp # copy the user's main entry point code

RUN g++ -O3 -std=c++17 userCodeMain.cpp -o exchange_engine -pthread

FROM gcr.io/distroless/static-debian12:latest

WORKDIR /app
COPY --from=builder /build/exchange_engine .

USER 65534:65534

EXPOSE 8888

ENTRYPOINT ["./exchange_engine"]
