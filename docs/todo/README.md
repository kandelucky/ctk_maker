# TODO — სამუშაო სისტემა

ეს ფოლდერი ცვლის ძველ `TODO.md`-ს. 6 ფაილია, რომლებიც სხვადასხვა სტატუსის ჩანაწერებს ინახავს.

## ფაილები

| ფაილი | რას შეიცავს |
|-------|-------------|
| [roadmap.md](roadmap.md) | **დაგეგმილი** ფაზები — committed სამუშაო, რიგი აქვს |
| [ideas.md](ideas.md) | **მომავლის იდეები** — exploratory, არ არის დაგეგმილი |
| [bugs.md](bugs.md) | **გასასწორებელი ბაგები** — რეალური ბაგები, გვიშლის ხელს |
| [observations.md](observations.md) | **დაკვირვებები** — უცნაური behavior, არ გვიშლის, "ეგებ ბაგია?" |
| [done.md](done.md) | **შესრულებული** ფაზები — არქივი თარიღით/ვერსიით |
| [reference.md](reference.md) | **საცნობარო** მასალა — Qt Designer map, Lucide icons |

## სქემა

### 1. ახალი task ჩნდება

- **დაგეგმილი / committed** → `roadmap.md`
- **მომავლის idea / exploratory** → `ideas.md`

### 2. სამუშაო იწყება

- `roadmap.md`-ში ფაზის header-ს ემატება `🚧 Active` marker

### 3. დასრულდა

- ფაზა გადადის `done.md`-ში **ერთი ხაზის შემაჯამებელი**-ით (date + version)
- დეტალები ინახება git history-ში (`git log --oneline`)

### 4. Bug იპოვა

- **ხელს გვიშლის / blocker** → `bugs.md` (repro steps + hypothesis)
- **არ გვიშლის, უცნაურია** → `observations.md`

### 5. Bug fix

- `bugs.md`-დან გადადის `done.md`-ში fix-ის შემდეგ
- `observations.md`-დან მხოლოდ მაშინ გადადის, თუ გამოიკვლია და გადაწყდა

## წესი

- **ერთი ფაილი = ერთი სტატუსი.** ჩანაწერი ერთდროულად ორგან არ იდება.
- **`done.md`-ში არქივი compact-ია.** ფაზა = ერთი header + 1-2 ხაზი. სრული დეტალები git history-ში.
- **`roadmap.md` + `ideas.md` ვრცლად.** იქ გადაწყვეტილება ჯერ არ მიღებულია.
- **`bugs.md` ყოველთვის repro steps-ით.** hypothesis + investigation ველები.
- **თარიღი ყოველთვის ISO format-ში** (`2026-04-21`).
