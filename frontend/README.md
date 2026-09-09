# Frontend preview

From this directory, run:

```sh
npm install
npm start
```

Open http://localhost:3000. The root URL opens the sign-in page. Successful
sign-in takes you to `/dashboard`. Visit `/signup` to create an account, or
`/dashboard` to preview the dashboard layout directly.

The dashboard layout can be viewed without the backend. Uploads, saved papers,
notes, summaries, and chat require the backend at http://localhost:8000 and a
signed-in user. Opening the dashboard does not bypass backend authorization.

Run `npm run build` to create a production build. Styling uses Tailwind CSS 3
through Create React App's built-in Tailwind support.
