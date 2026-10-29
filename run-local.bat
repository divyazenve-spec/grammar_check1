@echo off
REM ==============================================================================
REM Zenve Vet - Local Development Environment Launcher
REM Starts:
REM   1. LanguageTool Autocorrection Service (port 8000)
REM   2. Spring Boot Backend (port 8080)
REM   3. React Vite Frontend (port 5173)
REM ==============================================================================

echo [1/3] Starting LanguageTool Autocorrection Service on http://127.0.0.1:8000 ...
start "Zenve Vet - LanguageTool Autocorrection" cmd /k "cd autocorrect_service && python server.py"

echo [2/3] Starting Zenve Vet Spring Boot Backend on http://localhost:8080 ...
start "Zenve Vet - Spring Boot Backend" cmd /k "set JAVA_HOME=C:\Program Files\Eclipse Adoptium\jdk-21.0.12.101-hotspot&& set SPRING_DATASOURCE_URL=jdbc:h2:file:./data/zenvevet;DB_CLOSE_DELAY=-1;MODE=MySQL&& set SPRING_DATASOURCE_DRIVER_CLASS_NAME=org.h2.Driver&& set SPRING_DATASOURCE_USERNAME=sa&& set SPRING_DATASOURCE_PASSWORD=&& set UPLOAD_DIR=uploads&& cd server && .\mvnw.cmd spring-boot:run"

echo [3/3] Starting Zenve Vet React Client on http://localhost:5173 ...
start "Zenve Vet - React Vite Client" cmd /k "cd client && npm run dev"

echo.
echo ==============================================================================
echo [SUCCESS] Zenve Vet with LanguageTool Autocorrection is now starting!
echo  - Frontend Web UI:            http://localhost:5173
echo  - Autocorrection API:         http://127.0.0.1:8000/api/correct
echo  - Backend REST API:           http://localhost:8080/api/v1
echo ==============================================================================
