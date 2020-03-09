import csv
from datetime import datetime

DATA_OUTPUT = '../data/'

def create_mobile_library_file(organisation, filename, mobiles):
	with open(DATA_OUTPUT + filename, 'w', encoding='utf8', newline='') as out_csv:

		mobiles = sorted(mobiles, key=lambda row: (row[1], row[2], datetime.strptime('01/01/2020 ' + row[11], '%d/%m/%Y %H:%M')))
		mob_writer = csv.writer(out_csv, delimiter=',',
		                        quotechar='"', quoting=csv.QUOTE_MINIMAL)
		mob_writer.writerow(['organisation', 'mobile', 'route', 'community', 'stop', 'address', 'postcode', 'geox',
                       'geoy', 'day', 'type', 'arrival', 'departure', 'frequency', 'start', 'end', 'exceptions', 'timetable'])
		for sto in mobiles:
			mob_writer.writerow([organisation, sto[0], sto[1], sto[2], sto[3], sto[4], sto[5], sto[6],
                            sto[7], sto[8], sto[9], sto[10], sto[11], sto[12], sto[13], sto[14], sto[15], sto[16]])
