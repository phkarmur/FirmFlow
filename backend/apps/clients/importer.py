import io
import csv
import openpyxl
from rest_framework.exceptions import ValidationError
from apps.clients.models import Client, ClientContact
from apps.clients.validators import validate_pan_format, validate_gstin_format
from apps.accounts.models import Firm
from apps.common.models import AuditLog

class ClientSpreadsheetImporter:
    """
    Imports clients and primary contacts from CSV or XLSX files (§5.5 B5).
    Validates row by row, creates valid rows, and returns error report.
    """

    @classmethod
    def parse_file(cls, uploaded_file):
        """Yields list of dicts from CSV or XLSX file."""
        name = uploaded_file.name.lower()
        rows = []
        if name.endswith('.csv'):
            decoded = uploaded_file.read().decode('utf-8-sig')
            reader = csv.DictReader(io.StringIO(decoded))
            for r in reader:
                rows.append({k.strip(): (v.strip() if v else '') for k, v in r.items() if k})
        elif name.endswith(('.xlsx', '.xls')):
            wb = openpyxl.load_workbook(uploaded_file, data_only=True)
            sheet = wb.active
            headers = [str(cell.value or '').strip() for cell in sheet[1]]
            for row in sheet.iter_rows(min_row=2, values_only=True):
                if not any(row):
                    continue
                row_dict = {}
                for idx, val in enumerate(row):
                    if idx < len(headers) and headers[idx]:
                        row_dict[headers[idx]] = str(val or '').strip()
                rows.append(row_dict)
        else:
            raise ValidationError('File format not supported. Please upload a .csv or .xlsx file.')
        return rows

    @classmethod
    def import_clients(cls, firm: Firm, uploaded_file, user=None):
        rows = cls.parse_file(uploaded_file)
        created_clients = []
        errors = []

        for row_num, row in enumerate(rows, start=2):
            client_name = row.get('Client Name') or row.get('Name') or row.get('name')
            if not client_name:
                errors.append({'row': row_num, 'error': 'Missing client name.'})
                continue

            raw_pan = row.get('PAN') or row.get('pan') or ''
            raw_gstin = row.get('GSTIN') or row.get('gstin') or ''
            client_type = (row.get('Client Type') or row.get('type') or 'company').lower()
            email = row.get('Email') or row.get('email') or ''
            phone = row.get('Phone') or row.get('phone') or ''
            contact_name = row.get('Contact Person') or row.get('Contact Name') or ''

            # Validations
            clean_pan = ''
            if raw_pan:
                try:
                    clean_pan = validate_pan_format(raw_pan)
                except Exception as e:
                    errors.append({'row': row_num, 'client': client_name, 'error': f'Invalid PAN: {str(e)}'})
                    continue

            clean_gstin = ''
            if raw_gstin:
                try:
                    clean_gstin = validate_gstin_format(raw_gstin, clean_pan)
                except Exception as e:
                    errors.append({'row': row_num, 'client': client_name, 'error': f'Invalid GSTIN: {str(e)}'})
                    continue

            state_code = clean_gstin[:2] if clean_gstin else (row.get('State Code') or '')

            if clean_pan:
                from apps.common.crypto import pan_blind_index
                same_pan = Client.objects.filter(firm=firm, pan_hash=pan_blind_index(clean_pan)).exclude(name=client_name).first()
                if same_pan:
                    errors.append({'row': row_num, 'client': client_name,
                                   'error': f'PAN already belongs to existing client "{same_pan.name}".'})
                    continue

            # Create or update client
            client, created = Client.objects.get_or_create(
                firm=firm,
                name=client_name,
                defaults={
                    'client_type': client_type if client_type in dict(Client.ClientType.choices) else Client.ClientType.COMPANY,
                    'gstin': clean_gstin,
                    'email': email,
                    'phone': phone,
                    'state_code': state_code,
                }
            )
            if clean_pan:
                client.set_pan(clean_pan)
                client.save()

            if contact_name:
                ClientContact.objects.get_or_create(
                    client=client,
                    name=contact_name,
                    defaults={'email': email, 'phone': phone, 'is_primary': True}
                )

            created_clients.append(client.name)

        AuditLog.log(
            firm_id=firm.id,
            action='client.bulk_import',
            entity_type='Client',
            entity_id=str(firm.id),
            actor_user_id=user.id if user else None,
            new_value={'imported_count': len(created_clients), 'error_count': len(errors)}
        )

        return {
            'imported_count': len(created_clients),
            'errors': errors,
            'clients': created_clients,
        }

    @classmethod
    def generate_template_csv(cls):
        """Generates starter template CSV for client bulk import."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Client Name', 'Client Type', 'PAN', 'GSTIN', 'Email', 'Phone', 'Contact Person', 'State Code'])
        writer.writerow(['Apex Tech Pvt Ltd', 'company', 'AABCA1234F', '27AABCA1234F1Z9', 'accounts@apex.com', '9820012345', 'Ramesh Mehra', '27'])
        writer.writerow(['Rajesh Gupta HUF', 'huf', 'AABHR9999M', '', 'rajesh@gupta.com', '9988776655', 'Rajesh Gupta', '07'])
        return output.getvalue()
