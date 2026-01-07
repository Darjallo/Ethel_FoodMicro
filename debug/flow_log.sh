POD_EF=$(microk8s kubectl -n default get pod -l app=ethelflow -o jsonpath='{.items[0].metadata.name}')
echo "ETHELFLOW POD=$POD_EF"
microk8s kubectl -n default logs "$POD_EF" --since=5m --tail=300

POD_REA=$(microk8s kubectl -n default get pod -l app=reasoning -o jsonpath='{.items[0].metadata.name}')
echo "REASONING POD=$POD_REA"
microk8s kubectl -n default logs "$POD_REA" --since=5m --tail=300

