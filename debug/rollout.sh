cd ~/EthelService/ethelflow
sudo docker build --no-cache -f ethelflow.Dockerfile -t ethelflow:latest .
sudo docker save ethelflow:latest | microk8s ctr image import -
kubectl -n default rollout restart deployment ethelflow
kubectl -n default rollout status deployment ethelflow

