export async function api(path, options={}) {
  const response = await fetch('/api'+path, {
    ...options, credentials:'same-origin',
    headers:{...(options.body && typeof options.body==='string' ? {'Content-Type':'application/json'} : {}), ...options.headers}
  });
  const value = await response.json().catch(()=>({}));
  if (!response.ok) {
    const error = new Error(value.error || (typeof value.detail==='string' ? value.detail : 'Please check the fields and try again.'));
    error.status=response.status;
    throw error;
  }
  return value;
}
export const date = value => new Date(value*1000).toLocaleString([], {dateStyle:'medium',timeStyle:'short'});
export const label = value => value==='grace_recovered' ? 'Grace recovered' : value==='on_time' ? 'On time' : value;
