-- wrk POST script: sends JSON body to /items
wrk.method = "POST"
wrk.headers["Content-Type"] = "application/json"
wrk.body = '{"id":1,"name":"Widget","price":9.99}'
