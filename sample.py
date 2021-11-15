from rasa.shared.importers.rasa import RasaFileImporter
import asyncio
importer = RasaFileImporter.load_from_config(config_path="./tests/testing_data/yml_training_files/config.yml",
                                                         domain_path="./tests/testing_data/yml_training_files/domain.yml",
                                                         training_data_paths="./tests/testing_data/yml_training_files/data")
loop = asyncio.new_event_loop()
domain = loop.run_until_complete(importer.get_domain())