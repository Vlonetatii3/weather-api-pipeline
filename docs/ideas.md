# Ideas fuera de alcance

Cosas que "serían lindas" pero no entran en el alcance actual del proyecto.

- **Docker rootless**: hoy el usuario está en el grupo `docker` (equivale a root). Probar el modo rootless para no darle privilegios de root al daemon.
- **Caché con tamaño máximo**: `TTLCache` crece sin límite (solo borra entradas vencidas cuando se las lee). Con muchas ciudades distintas podría usar mucha memoria; agregar un máximo con desalojo LRU.
- **Evitar cache stampede**: si llegan N requests simultáneos por la misma ciudad sin caché, se hacen N llamadas a Open-Meteo. Se puede resolver con un lock por clave ("single-flight").
- **Jitter en el backoff**: sumar un componente aleatorio al tiempo entre reintentos para que muchas instancias no reintenten todas sincronizadas.
