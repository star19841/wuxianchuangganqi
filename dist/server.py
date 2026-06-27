import socket
import threading

LISTEN_IP='0.0.0.0'
LISTEN_PORT = 8888

def handle_client(conn,addr):
	print(f"[Server]AI智能终端盒子上线，Addr:{addr}")
	welcome = "服务端就绪：支持：On/off/status"
	while True:
		try:
			raw = conn.recv(64)
			if not raw:
				break
			msg = raw.decode('utf-8').strip()
			print(f"[Server]-{addr}-盒子反馈：{msg}")
			if msg in "box_id":
				print("box_id上线")
		except Exception as e:
			print(f"[Server]-{addr}-盒子连接异常：{e}")
			break
	conn.close()
			
def send_command(sock,cmd):
	sock.sendall(f"{cmd}\n.encode('utf-8')")

def server_loop():
	sock = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
	sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
	sock.bind((LISTEN_IP,LISTEN_PORT))
	sock.listen(5)
	print("[Server]Tcp服务启动，等待AI智能终端盒子连接...")
	client_conn = None

	while True:
		conn,addr = sock.accept()
		client_conn =conn
		threading.Thread(target=handle_client,args=(conn,addr),daemon=True).start()
		while client_conn:
			print("[AI盒子]控制面板")
			cmdlist = """
On-打开LED
Off-关灯
Status-查询灯的状态
exit-断开并退出"""
			print(cmdlist)
			user_cmd = input("请输入指令：").strip()
			if user_cmd.lower() =="exit":
				client_conn.close()
				client_conn = None
				print("断开设备，等待重连...")
				break
			elif user_cmd.lower() in ["on","off","status"]:
				send_command(client_conn,user_cmd.lower())
			else:
				print("[AI盒子]无效指令，请重新输入")

if __name__ == '__main__':
	server_loop()