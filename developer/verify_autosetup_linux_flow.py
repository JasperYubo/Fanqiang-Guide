"""Opt-in Linux device-flow smoke using a verified binary and loopback-only fixtures."""
from __future__ import annotations
import argparse, base64, hashlib, http.server, json, os, pathlib, secrets, socket, socketserver, ssl, struct, subprocess, tempfile, threading, time
from datetime import datetime, timezone

def available_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]

def network_fingerprint():
    routes = subprocess.check_output(["ip", "-j", "route", "show", "table", "all"])
    dns = pathlib.Path("/etc/resolv.conf").read_bytes()
    return {"routes_sha256": hashlib.sha256(routes).hexdigest(), "resolv_conf_sha256": hashlib.sha256(dns).hexdigest()}

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--binary", type=pathlib.Path, required=True)
    ap.add_argument("--book", type=pathlib.Path, required=True)
    ap.add_argument("--output", type=pathlib.Path, required=True)
    args = ap.parse_args()
    assert not args.output.exists(), "Evidence output must be new"
    assert os.name == "posix"
    before = network_fingerprint()
    payload = ("fanqiang-autosetup-target-" + secrets.token_hex(16)).encode()
    hits, dns_queries, processes, handles = [], [], [], []
    report = {"started_at":datetime.now(timezone.utc).isoformat(), "platform":"Linux amd64",
              "book_sha256":hashlib.sha256(args.book.read_bytes()).hexdigest(),
              "version":subprocess.check_output([str(args.binary),"version"],text=True).splitlines()[0],
              "scope":"isolated loopback SOCKS application -> Shadowsocks TCP -> HTTPS fixture; IPv4; server-side test DNS",
              "not_tested":["Windows","Android","iOS","macOS","router","TUN","system-wide routing","IPv6","UDP proxy","public node availability"],
              "steps":[], "ok":False}
    server = dns_server = None
    ports = []
    with tempfile.TemporaryDirectory(prefix="autosetup-flow-") as temp:
        root=pathlib.Path(temp)
        root.chmod(0o700)
        secret=base64.b64encode(secrets.token_bytes(32)).decode()
        key=root/"tls.key"
        cert=root/"tls.crt"
        p=subprocess.run(["openssl","req","-x509","-newkey","rsa:2048","-nodes","-days","1",
                          "-keyout",str(key),"-out",str(cert),"-subj","/CN=autosetup-test.invalid",
                          "-addext","subjectAltName=DNS:autosetup-test.invalid"],capture_output=True)
        assert p.returncode==0, "test certificate generation failed"
        key.chmod(0o600)

        class Target(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                hits.append(self.path)
                self.send_response(200)
                self.send_header("Content-Length",str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            def log_message(self,*a): pass

        class DNS(socketserver.BaseRequestHandler):
            def handle(self):
                data,sock=self.request
                try:
                    offset,labels=12,[]
                    while data[offset]:
                        n=data[offset]; offset+=1
                        labels.append(data[offset:offset+n].decode("ascii")); offset+=n
                    offset+=1
                    qtype,qclass=struct.unpack("!HH",data[offset:offset+4]); end=offset+4
                    domain=".".join(labels)
                    dns_queries.append({"name":domain,"type":qtype})
                    answer=b""
                    if domain=="autosetup-test.invalid" and qtype==1 and qclass==1:
                        answer=b"\xc0\x0c"+struct.pack("!HHIH",1,1,30,4)+socket.inet_aton("127.0.0.1")
                    response=data[:2]+struct.pack("!HHHHH",0x8180,1,int(bool(answer)),0,0)+data[12:end]+answer
                    sock.sendto(response,self.client_address)
                except (IndexError,UnicodeError,struct.error): pass

        def stop(p):
            if p and p.poll() is None:
                p.terminate()
                try: p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    p.kill(); p.wait(timeout=5)

        def save(name,config):
            f=root/name
            with f.open("w") as h: json.dump(config,h)
            f.chmod(0o600)
            checked=subprocess.run([str(args.binary),"check","-c",str(f)],capture_output=True,text=True)
            assert checked.returncode==0, "sing-box configuration validation failed: "+checked.stderr.replace(secret,"[redacted]")[:800]
            return f

        def start(name,config,port):
            f=save(name+".json",config)
            h=(root/(name+".log")).open("wb"); handles.append(h)
            p=subprocess.Popen([str(args.binary),"run","-c",str(f)],stdout=h,stderr=subprocess.STDOUT)
            processes.append(p)
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                assert p.poll() is None, name+" exited"
                try:
                    with socket.create_connection(("127.0.0.1",port),timeout=.2): return p
                except OSError: time.sleep(.05)
            raise AssertionError(name+" listener not ready")

        def fetch(proxy_port,target_port):
            env={k:v for k,v in os.environ.items() if k.lower() not in ("http_proxy","https_proxy","all_proxy","no_proxy")}
            return subprocess.run(["curl","--silent","--show-error","--max-time","8","--noproxy","",
                "--proxy",f"socks5h://127.0.0.1:{proxy_port}","--cacert",str(cert),
                f"https://autosetup-test.invalid:{target_port}/verified-content"],capture_output=True,env=env)

        try:
            server=http.server.ThreadingHTTPServer(("127.0.0.1",0),Target)
            ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(str(cert),str(key))
            server.socket=ctx.wrap_socket(server.socket,server_side=True)
            threading.Thread(target=server.serve_forever,daemon=True).start()
            dns_server=socketserver.ThreadingUDPServer(("127.0.0.1",0),DNS)
            threading.Thread(target=dns_server.serve_forever,daemon=True).start()
            ss_port,socks_port,bad_port=available_port(),available_port(),available_port()
            ports=[ss_port,socks_port]
            target_port=server.server_address[1]
            server_config={"log":{"level":"info","timestamp":False},
                "dns":{"servers":[{"type":"udp","tag":"test-dns","server":"127.0.0.1","server_port":dns_server.server_address[1]}]},
                "inbounds":[{"type":"shadowsocks","tag":"ss-in","listen":"127.0.0.1","listen_port":ss_port,
                    "method":"2022-blake3-aes-256-gcm","password":secret,"network":"tcp"}],
                "outbounds":[{"type":"direct","tag":"direct"}],
                "route":{"final":"direct","default_domain_resolver":"test-dns"}}
            client_config={"log":{"level":"info","timestamp":False},
                "inbounds":[{"type":"socks","tag":"app-socks","listen":"127.0.0.1","listen_port":socks_port}],
                "outbounds":[{"type":"shadowsocks","tag":"tested-node","server":"127.0.0.1","server_port":bad_port,
                    "method":"2022-blake3-aes-256-gcm","password":secret,"network":"tcp"}],
                "route":{"final":"tested-node"}}
            ss=start("server",server_config,ss_port)
            client=start("client-bad",client_config,socks_port)
            failed=fetch(socks_port,target_port)
            assert failed.returncode!=0 and not hits
            report["steps"].append({"name":"detect_wrong_node_port","pass":True,"curl_exit":failed.returncode,
                "finding":"configured port differs from observed listening endpoint; not attributed to censorship"})
            stop(client)
            client_config["outbounds"][0]["server_port"]=ss_port
            client=start("client-repaired",client_config,socks_port)
            good=fetch(socks_port,target_port)
            assert good.returncode==0 and good.stdout==payload, good.stderr.decode(errors="replace")[:500]
            assert any(x["name"]=="autosetup-test.invalid" and x["type"]==1 for x in dns_queries)
            report["steps"].append({"name":"single_change_repair_and_real_content","pass":True,
                "tls_certificate_validation":True,"expected_body_sha256":hashlib.sha256(payload).hexdigest(),
                "server_side_dns_observed":True})
            stop(client)
            stopped=fetch(socks_port,target_port)
            assert stopped.returncode!=0
            report["steps"].append({"name":"disconnected_path_fails","pass":True})
            client=start("client-reconnected",client_config,socks_port)
            again=fetch(socks_port,target_port)
            assert again.returncode==0 and again.stdout==payload
            report["steps"].append({"name":"reconnect_and_repeat","pass":True})
            for h in handles: h.flush()
            server_log=(root/"server.log").read_text()
            client_log=(root/"client-repaired.log").read_text()
            assert "inbound/shadowsocks[ss-in]" in server_log and "outbound/shadowsocks[tested-node]" in client_log
            assert "autosetup-test.invalid" in server_log
            report["route_evidence"]={"client_shadowsocks_outbound":True,"server_shadowsocks_inbound":True,
                                      "server_target_domain":True,"target_requests":len(hits),"dns_queries":dns_queries}
            report["ok"]=True
        finally:
            for p in reversed(processes): stop(p)
            for h in handles: h.close()
            if server: server.shutdown(); server.server_close()
            if dns_server: dns_server.shutdown(); dns_server.server_close()
            report["processes_stopped"]=all(p.poll() is not None for p in processes)
            report["network_unchanged"]=before==network_fingerprint()
            report["secrets_in_evidence"]=secret in json.dumps(report)
            report["finished_at"]=datetime.now(timezone.utc).isoformat()
            report["ok"]=report["ok"] and report["processes_stopped"] and report["network_unchanged"] and not report["secrets_in_evidence"]
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report))
    if not report["ok"]: raise SystemExit(1)
if __name__=="__main__": main()
