# Event Bus

> The pub/sub mechanism that decouples the model from the views.

## Why an event bus

TODO: Panels must not hold direct references to each other, otherwise any
feature touches every panel. The bus is the one allowed coupling point.

## API

TODO: Document `subscribe(topic, handler)`, `publish(topic, payload)`,
and `unsubscribe`. Source: [app/core/event_bus.py](../../app/core/event_bus.py).

## Topics

TODO: Enumerate all topic strings currently in use (e.g. `selection.changed`,
`widget.added`, `widget.property.changed`, `project.loaded`).

## Example flow

TODO: Walk through a single user action — e.g. editing a color in the
Properties panel — and trace every publish/subscribe hop.

## Threading

TODO: All publishes happen on the Tk main thread. Document why.

## Pitfalls

TODO: Subscription leaks, re-entrant publishes, ordering assumptions.
