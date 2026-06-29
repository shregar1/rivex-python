export interface Endpoint {
  id: string;
  method: string;
  path: string;
  summary: string;
  params: any[];
  requestBody?: any;
  responses: Record<string, any>;
  usedSchemas: Record<string, any>;
}

export function generateCurl(e: Endpoint, specUrl: string, inputs: Record<string, string>, reqBody?: string, authHeader?: string): string {
  let url = specUrl.replace('/openapi.json', '') + e.path;
  const qp = new URLSearchParams();
  let curl = `curl -X ${e.method} `;
  
  const headers: string[] = ['-H "Accept: application/json"'];
  if (authHeader) headers.push(`-H "Authorization: ${authHeader}"`);
  
  e.params.forEach(p => {
    const val = inputs[p.name];
    if (val) {
      if (p.in === 'path') url = url.replace(`{${p.name}}`, encodeURIComponent(val));
      if (p.in === 'query') qp.append(p.name, val);
      if (p.in === 'header') headers.push(`-H "${p.name}: ${val.replace(/"/g, '\\"')}"`);
    }
  });
  
  if (qp.toString()) url += '?' + qp.toString();
  curl += `"${url}" `;
  
  if (e.requestBody && reqBody) {
    headers.push('-H "Content-Type: application/json"');
    curl += `-d '${reqBody.replace(/'/g, "'\\''")}' `;
  }
  
  curl += headers.join(' ');
  return curl;
}

export function generatePython(e: Endpoint, specUrl: string, inputs: Record<string, string>, reqBody?: string, authHeader?: string): string {
  let url = specUrl.replace('/openapi.json', '') + e.path;
  const qp = new URLSearchParams();
  
  const headers: Record<string, string> = { "Accept": "application/json" };
  if (authHeader) headers["Authorization"] = authHeader;
  
  e.params.forEach(p => {
    const val = inputs[p.name];
    if (val) {
      if (p.in === 'path') url = url.replace(`{${p.name}}`, encodeURIComponent(val));
      if (p.in === 'query') qp.append(p.name, val);
      if (p.in === 'header') headers[p.name] = val;
    }
  });

  if (e.requestBody && reqBody) {
      headers["Content-Type"] = "application/json";
  }
  
  let py = `import requests\n\n`;
  py += `url = "${url}"\n`;
  
  if (qp.toString()) {
      py += `params = {`;
      for (const [k, v] of qp.entries()) py += `"${k}": "${v}", `;
      py += `}\n`;
  }
  
  py += `headers = ${JSON.stringify(headers, null, 4)}\n`;
  
  if (e.requestBody && reqBody) {
      let prettyBody = reqBody;
      try { prettyBody = JSON.stringify(JSON.parse(reqBody), null, 4); } catch {}
      py += `\npayload = ${prettyBody.replace(/true/g, 'True').replace(/false/g, 'False').replace(/null/g, 'None')}\n`;
  }
  
  py += `\nresponse = requests.${e.method.toLowerCase()}(url, headers=headers`;
  if (qp.toString()) py += `, params=params`;
  if (e.requestBody && reqBody) py += `, json=payload`;
  py += `)\n\nprint(response.json())`;
  
  return py;
}

export function generateJS(e: Endpoint, specUrl: string, inputs: Record<string, string>, reqBody?: string, authHeader?: string): string {
  let url = specUrl.replace('/openapi.json', '') + e.path;
  const qp = new URLSearchParams();
  
  const headers: Record<string, string> = { "Accept": "application/json" };
  if (authHeader) headers["Authorization"] = authHeader;
  
  e.params.forEach(p => {
    const val = inputs[p.name];
    if (val) {
      if (p.in === 'path') url = url.replace(`{${p.name}}`, encodeURIComponent(val));
      if (p.in === 'query') qp.append(p.name, val);
      if (p.in === 'header') headers[p.name] = val;
    }
  });

  if (e.requestBody && reqBody) headers["Content-Type"] = "application/json";
  if (qp.toString()) url += '?' + qp.toString();
  
  let js = `fetch('${url}', {\n`;
  js += `  method: '${e.method}',\n`;
  js += `  headers: ${JSON.stringify(headers, null, 2).replace(/\n/g, '\n  ')}`;
  
  if (e.requestBody && reqBody) {
      let prettyBody = reqBody;
      try { prettyBody = JSON.stringify(JSON.parse(reqBody), null, 2); } catch {}
      js += `,\n  body: JSON.stringify(${prettyBody.replace(/\n/g, '\n  ')})`;
  }
  
  js += `\n})\n.then(res => res.json())\n.then(console.log)\n.catch(console.error);`;
  return js;
}
