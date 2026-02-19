#!/usr/bin/env python3
"""
CML (Cloudera Machine Learning) Application Entry Point

This script serves as the entry point for deploying the CIS Trade Hive
Django application as a CML Project Application.

CML Application Configuration:
- Script: config/cml_app.py
- Subdomain: cis-trade-hive (or your preferred subdomain)
- Description: CIS Trade Management System

Environment Variables (set in CML Project Settings):
- HIVE_HOST: HiveServer2 hostname (e.g., your-cloudera-host)
- HIVE_PORT: HiveServer2 port (default: 10000)
- HIVE_DB: Database name (default: gmp_cis)
- HIVE_AUTH: Authentication method (NONE, LDAP, KERBEROS)
- HIVE_USERNAME: Hive username
- HIVE_PASSWORD: Hive password
- DJANGO_SECRET_KEY: Django secret key for production
- DJANGO_DEBUG: Set to 'false' for production
- DJANGO_ALLOWED_HOSTS: Comma-separated list of allowed hosts

Usage:
    CML will execute this script to start the application.
    The application will be accessible via the CML application URL.
"""

import os
import sys
import subprocess
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def setup_virtual_environment():
    """
    Set up and activate virtual environment for CML.
    CML provides a Python runtime, but we ensure dependencies are installed.
    """
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    venv_dir = os.path.join(project_dir, '.venv')
    requirements_file = os.path.join(project_dir, 'requirements.txt')

    # Check if virtual environment exists, if not create it
    if not os.path.exists(venv_dir):
        logger.info("Creating virtual environment...")
        subprocess.run([sys.executable, '-m', 'venv', venv_dir], check=True)
        logger.info("Virtual environment created successfully")

    # Determine the pip executable path
    if sys.platform == 'win32':
        pip_executable = os.path.join(venv_dir, 'Scripts', 'pip')
        python_executable = os.path.join(venv_dir, 'Scripts', 'python')
    else:
        pip_executable = os.path.join(venv_dir, 'bin', 'pip')
        python_executable = os.path.join(venv_dir, 'bin', 'python')

    # Install/upgrade pip
    logger.info("Upgrading pip...")
    subprocess.run([python_executable, '-m', 'pip', 'install', '--upgrade', 'pip'], check=True)

    # Install requirements
    if os.path.exists(requirements_file):
        logger.info("Installing dependencies from requirements.txt...")
        subprocess.run([pip_executable, 'install', '-r', requirements_file], check=True)
        logger.info("Dependencies installed successfully")
    else:
        logger.warning(f"requirements.txt not found at {requirements_file}")

    return python_executable


def setup_environment_variables():
    """
    Set up environment variables for CML deployment.
    These can be overridden by CML project environment variables.
    """
    # Get CML-specific environment variables
    cml_app_port = os.environ.get('CDSW_APP_PORT', '8080')
    cml_domain = os.environ.get('CDSW_DOMAIN', '')

    # Set Django-specific environment variables with CML defaults
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    os.environ.setdefault('DJANGO_DEBUG', 'false')  # Production default
    os.environ.setdefault('DJANGO_SECRET_KEY', os.environ.get('DJANGO_SECRET_KEY', 'cml-production-secret-key-change-me'))

    # Build allowed hosts for CML
    allowed_hosts = ['localhost', '127.0.0.1', '0.0.0.0']
    if cml_domain:
        allowed_hosts.append(cml_domain)
        allowed_hosts.append(f'*.{cml_domain}')
    existing_hosts = os.environ.get('DJANGO_ALLOWED_HOSTS', '')
    if existing_hosts:
        allowed_hosts.extend(existing_hosts.split(','))
    os.environ['DJANGO_ALLOWED_HOSTS'] = ','.join(set(allowed_hosts))

    # Hive configuration defaults for Cloudera
    os.environ.setdefault('HIVE_HOST', os.environ.get('HIVE_HOST', 'localhost'))
    os.environ.setdefault('HIVE_PORT', os.environ.get('HIVE_PORT', '10000'))
    os.environ.setdefault('HIVE_DB', os.environ.get('HIVE_DB', 'gmp_cis'))
    os.environ.setdefault('HIVE_AUTH', os.environ.get('HIVE_AUTH', 'NONE'))

    logger.info(f"CML App Port: {cml_app_port}")
    logger.info(f"CML Domain: {cml_domain}")
    logger.info(f"Hive Host: {os.environ.get('HIVE_HOST')}")
    logger.info(f"Hive Port: {os.environ.get('HIVE_PORT')}")
    logger.info(f"Hive Database: {os.environ.get('HIVE_DB')}")

    return cml_app_port


def collect_static_files(python_executable, project_dir):
    """
    Collect static files for production deployment.
    """
    manage_py = os.path.join(project_dir, 'manage.py')
    if os.path.exists(manage_py):
        logger.info("Collecting static files...")
        try:
            subprocess.run(
                [python_executable, manage_py, 'collectstatic', '--noinput'],
                check=True,
                cwd=project_dir
            )
            logger.info("Static files collected successfully")
        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to collect static files: {e}")


def run_migrations(python_executable, project_dir):
    """
    Run database migrations if needed.
    Note: This project uses Hive, so Django migrations are minimal.
    """
    manage_py = os.path.join(project_dir, 'manage.py')
    if os.path.exists(manage_py):
        logger.info("Running database migrations...")
        try:
            subprocess.run(
                [python_executable, manage_py, 'migrate', '--noinput'],
                check=True,
                cwd=project_dir
            )
            logger.info("Migrations completed successfully")
        except subprocess.CalledProcessError as e:
            logger.warning(f"Migration warning (may be expected for Hive-only setup): {e}")


def start_gunicorn_server(python_executable, project_dir, port):
    """
    Start the Gunicorn WSGI server for production.
    """
    # Determine the gunicorn executable
    venv_dir = os.path.join(project_dir, '.venv')
    if sys.platform == 'win32':
        gunicorn_executable = os.path.join(venv_dir, 'Scripts', 'gunicorn')
    else:
        gunicorn_executable = os.path.join(venv_dir, 'bin', 'gunicorn')

    # Gunicorn configuration
    workers = int(os.environ.get('GUNICORN_WORKERS', '4'))
    threads = int(os.environ.get('GUNICORN_THREADS', '4'))
    timeout = int(os.environ.get('GUNICORN_TIMEOUT', '120'))

    gunicorn_cmd = [
        gunicorn_executable,
        'config.wsgi:application',
        '--bind', f'0.0.0.0:{port}',
        '--workers', str(workers),
        '--threads', str(threads),
        '--timeout', str(timeout),
        '--access-logfile', '-',
        '--error-logfile', '-',
        '--capture-output',
        '--enable-stdio-inheritance',
    ]

    logger.info(f"Starting Gunicorn server on port {port}...")
    logger.info(f"Workers: {workers}, Threads: {threads}, Timeout: {timeout}s")
    logger.info(f"Command: {' '.join(gunicorn_cmd)}")

    # Start Gunicorn (this will block and run the server)
    os.chdir(project_dir)
    os.execv(gunicorn_executable, gunicorn_cmd)


def main():
    """
    Main entry point for CML application deployment.
    """
    logger.info("=" * 60)
    logger.info("CIS Trade Hive - CML Application Startup")
    logger.info("=" * 60)

    # Get project directory
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    logger.info(f"Project directory: {project_dir}")

    # Change to project directory
    os.chdir(project_dir)

    # Setup environment variables
    port = setup_environment_variables()

    # Setup virtual environment and install dependencies
    python_executable = setup_virtual_environment()

    # Collect static files
    collect_static_files(python_executable, project_dir)

    # Run migrations (optional for Hive-only setup)
    run_migrations(python_executable, project_dir)

    # Start the server
    start_gunicorn_server(python_executable, project_dir, port)


if __name__ == '__main__':
    main()
