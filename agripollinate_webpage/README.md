# Agripollinate Web Application

This folder contains the web application for Agripollinate. It includes:
- **`farmer-dashboard/`** — React frontend
- **`farmer-dashboard-backend/`** — Express backend
- **Root package scripts** that start the frontend, backend, and ML service together

## Quick Start

From `agripollinate_webpage/`:

```bash
npm install
npm run setup
npm run dev
```

- `npm run setup` installs dependencies for the root package, frontend, backend, and ML service.
- `npm run dev` starts the complete system:
  - React frontend
  - Express backend
  - Python ML service

This is the command users should run to start the whole program.

## Project Structure

```
agripollinate_webpage/
├── farmer-dashboard/                # React frontend
│   ├── public/                      # Static files
│   ├── src/                         # React app source code
│   ├── App.jsx                      # Root application component
│   ├── main.jsx                     # Vite entry point
│   └── package.json                 # Frontend package and scripts
├── farmer-dashboard-backend/        # Express backend + ML integration
│   ├── server4.js                   # Main backend server
│   ├── batchCollector.js            # Event batch logic
│   ├── package.json                 # Backend package and scripts
│   └── ml/                          # Python ML service
│       ├── run.js                   # ML service launcher
│       ├── setup-ml.js              # ML environment helper
│       ├── ml.py                    # Python ML service entrypoint
│       └── best.pt                  # Trained ML model
├── package.json                     # Root scripts for running all services
└── README.md                        # This file
```

## Root Package Scripts

The root `package.json` coordinates the full web app:

- `npm run dev` — start frontend, backend, and ML service together
- `npm run dev:ml` — start only the ML service
- `npm run setup` — install dependencies and prepare the ML environment
- `npm run setup:ml` — create the Python virtual environment for ML
- `npm run setup:ml:install` — install ML Python dependencies

## Frontend

The frontend lives in `farmer-dashboard/`.

### Stack

- React 19.1.1
- Vite
- Tailwind CSS
- React Router 7.9
- Heroicons React
- TensorFlow.js
- @tensorflow-models/mobilenet

### Frontend Scripts

```bash
cd farmer-dashboard
npm install
npm run dev
npm run build
npm run preview
```

The development server runs by default at `http://localhost:5173`.

## Backend

The backend lives in `farmer-dashboard-backend/`.

### Stack

- Node.js
- Express.js
- CORS
- dotenv
- nodemon

### Backend Scripts

```bash
cd farmer-dashboard-backend
npm install
npm run dev
npm start
```

### Backend API Endpoints

Implemented in `server4.js`:

- `GET /images/list` — latest image pairs
- `GET /images/annotated` — latest annotated images
- `GET /images/lidar` — latest LiDAR heatmap images
- `POST /detect-image` — run detection on an image by filename
- `GET /api/batches` — list batch metadata

## ML Service

The ML service is launched from `farmer-dashboard-backend/ml/run.js`.

- Starts a Python process using the virtual environment at `farmer-dashboard-backend/ml/venv`
- Runs `ml.py`
- Uses `best.pt` for the trained model
- Default service URL: `http://localhost:5000`

## Setup and Run Guide

### Full installation

From `agripollinate_webpage/`:

```bash
npm install
npm run setup
```

### Run the complete application

From `agripollinate_webpage/`:

```bash
npm run dev
```

### Run only one part

Frontend only:
```bash
npm run dev --prefix farmer-dashboard
```

Backend only:
```bash
npm run dev --prefix farmer-dashboard-backend
```

ML service only:
```bash
npm run dev:ml
```

## Environment Variables

The backend can be configured with a `.env` file in `farmer-dashboard-backend/`.

Example:

```env
RASPBERRY_PI_HOST=10.250.76.217
RASPBERRY_PI_PORT=12345
PORT=3000
LOG_LEVEL=info
NODE_ENV=development
```

The frontend currently uses the default Vite configuration and does not require a separate `.env` file unless additional environment variables are added.

## Notes

- `npm run dev` at the root is the recommended command to run the full program.
- `npm run setup` should be run the first time to install all dependencies and initialize the ML environment.
- The backend does not require a build step; it runs directly with Node.

## Additional Documentation

- Backend README: `farmer-dashboard-backend/README.md`


## File Structures

### Frontend (`farmer-dashboard/src/`)

```
src/
├── App.jsx                    # Root component with routing
├── main.jsx                   # Application entry point
├── components/               # Reusable UI components
├── pages/                    # Page-level components
├── hooks/                    # Custom React hooks
├── state/                    # State management files
├── utils/                    # Helper utilities
├── styles/                   # CSS files and Tailwind
└── assets/                   # Images and icons
```

### Backend Configuration

Key files:
- `server4.js` - Main Express application
- `batchCollector.js` - Event aggregation logic
- `.env` - Environment configuration
- `package.json` - Dependencies and scripts
